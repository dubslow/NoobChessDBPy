#! python3.11, I think

#    Copyright (C) 2023 Dubslow
#
#    This module is a part of the noobchessdbpy package.
#
#    This program is libre software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
#    See the LICENSE file for more details.

'''
This module implements some standard CDB interaction algorithms, building atop the API.

Since we want to keep reusing one http client, the algorithms are all implemented as methods on a further subclass of the
API client: `AsyncCDBLibrary`. Create an instance of this class to use the algorithms. Arguments are generally `chess`
objects.

In addition to the main algorithms class, this module also exposes a static `parse_pgn_to_set` function, as well as
some helper classes `BreadthFirstState` and `CircularRequests`, and also the enum `CDBArgs` for use in scripts which
call this library.

Checkout the docstrings of all these things to get started -- or read the example scripts!
'''

########################################################################################################################

import math
from typing import Iterable

import chess
import chess.pgn
import trio
import traceback

from ..api import AsyncCDBClient, CDBStatus, strip_fen
from . import _chess_extensions
from ._stateful_iterators import BreadthFirstState, CircularRequesters, __all__ as _s_i_all__
from ._script_args import CDBArgs, __all__ as _s_a_all__
# The contents of _stateful_iterators are exposed via this module, but separate files for better focus when reading

__all__ = ['AsyncCDBLibrary', 'parse_pgn_to_set'] + _s_i_all__ + _s_a_all__

########################################################################################################################

class AsyncCDBLibrary(AsyncCDBClient):
    '''
    In general, we try to reuse a single client as much as possible, so algorithms are implemented
    as a subclass of the client.

    Unlike the API proper, this uses `trio` to provide an eventloop and task-management in most functions. Of course
    these algorithms can be re-implemented against any eventloop using the API.
    '''

    # Maybe we can later export static variations which construct a new client on each call?
    def __init__(self, **kwargs):
        '''This AsyncCDBClient subclass may be initialized with any kwargs of the parent class'''
        super().__init__(**kwargs)

    #
    ####################################################################################################################
    ####################################################################################################################
    # First, basic some examples of "flat" concurrency: spawn one task per input, ez, simple. The catch is that thousands
    # of inputs would spawn thousands of tasks, so this isn't useful for more than a few hundred requests.

    async def queue_single_line(self, pgn:chess.pgn.GameNode):
        '''Given a single line of moves, `queue` for analysis all positions in this line.'''
        # chess.pgn handles variations, and silently we don't actually verify if this pgn has no variations.
        n = 0
        async with trio.open_nursery() as nursery:
            for node in pgn.mainline():
                nursery.start_soon(self.queue, node.board())
                n += 1
        print(f"completed {n} queues")

    async def query_reverse_single_line(self, pgn:chess.pgn.GameNode):
        '''Given a single line of moves, `query` in reverse the positions to aid backpropagation.'''
        n = 0
        async with trio.open_nursery() as nursery:
            for node in reversed(pgn.mainline()):
                nursery.start_soon(self.query_all, node.board())
                n += 1
                await trio.sleep(0.001) # this doesn't guarantee order of query, but theoretically helps
        print(f"completed {n} queries")

    #
    ####################################################################################################################
    ####################################################################################################################
    # Next we implement some basic structure to use a standard concurrency to process large inputs, with thousands or
    # millions of requests, but a fixed amount of concurrency, where each task is recycled to process many requests.
    # This `mass_request` family operates on the basic principle that each request is quite independent of any other,
    # that the only goal is to do them all as fast as possible.

    # The first function here is the basic unit upon which others are built. It demonstrates intro-level usage of the
    #  core `trio` tools to implement structured concurrency.
    async def mass_request(self, api_call, producer_task, *producer_args, collect_results=False):
        '''
        Generic mass requester. Takes API call, producer task, producer args, and whether to collect results.
        The producer task MUST accept, and close when complete, its `send_taskqueue` trio.MemorySendChannel. Other args
        come after `send_taskqueue`.

        Constructs the consumer task to make the API call, and constructs the queue from producer to consumers.

        If collecting results, they're tuples of `(api_arg, api_call(api_arg))`. The caller can easily convert this to a
        dict if the arg is hashable.
        '''
        async with trio.open_nursery() as nursery:
            # in general, we use the "tasks close their channel" pattern
            send_taskqueue, recv_taskqueue = trio.open_memory_channel(self.concurrency)
            nursery.start_soon(producer_task, send_taskqueue, *producer_args)

            if collect_results:
                results = []
                send_serialize, recv_serialize = trio.open_memory_channel(self.concurrency)
                nursery.start_soon(self._serializer, recv_serialize, results)
                async with recv_taskqueue, send_serialize:
                    for i in range(self.concurrency):
                        nursery.start_soon(self._consumer_results, api_call, recv_taskqueue.clone(), send_serialize.clone())
            else:
                async with recv_taskqueue:
                    for i in range(self.concurrency):
                        nursery.start_soon(self._consumer, api_call, recv_taskqueue.clone())

        if collect_results:
            return results
        return

    @staticmethod
    async def _consumer(api_call, recv_taskqueue:trio.MemoryReceiveChannel):
        async with recv_taskqueue:
            async for thing in recv_taskqueue:
                await api_call(thing)

    @staticmethod
    async def _consumer_results(api_call, recv_taskqueue:trio.MemoryReceiveChannel,
                                          send_serialize:trio.MemorySendChannel):
        async with recv_taskqueue, send_serialize:
            async for thing in recv_taskqueue:
                result = (thing, await api_call(thing))
                await send_serialize.send(result)

    @staticmethod
    async def _serializer(recv_serialize, collector):
        # in theory, we shouldn't need the collector arg, instead making our own and returning it to the nursery...
        async with recv_serialize:
            async for val in recv_serialize:
                collector.append(val)

    ####################################################################################################################
    # Next we have various helpers built upon `self.mass_request`, showing how to customize it
    # TODO: factor out common code from all these producers?

    async def mass_query_fens(self, fens:Iterable):
        '''
        Very basic: given a container of FENs, query them all and return the CDB results. Can be used for arbitrarily
        large containers, so long as you don't hit the rate limit.
        '''
        # Note: for containers of size less than the concurrency, this can be quite wasteful. Alas, nurseries not
        # returning retvals by default makes it tougher...
        u = len(fens)
        print(f"now mass querying {u} positions")
        results = await self.mass_request(self.query_all, self._query_fen_producer, fens, collect_results=True)
        print(f"\nall {u} queries complete")
        return results

    @staticmethod
    async def _query_fen_producer(send_taskqueue:trio.MemorySendChannel, fens:Iterable):
        n = 0
        async with send_taskqueue:
            for fen in fens:
                await send_taskqueue.send(chess.Board(fen))
                n += 1
                if n & 0x3F == 0:
                    print(f"\rtaskqueued {n} requests", end='')


    async def mass_queue(self, all_positions:Iterable):
        '''
        Pretty much what the interface suggests. Given an iterable of positions, queue them all into the DB as fast as
        possible. Better hope you don't get rate limited lol
        '''
        u = len(all_positions)
        print(f"now mass queueing {u} positions")
        await self.mass_request(self.queue, self._iterable_reader, all_positions)
        print(f"\nall {u} positions have been queued for analysis")

    @staticmethod
    async def _iterable_reader(send_taskqueue:trio.MemorySendChannel, iterable):
        n = 0
        async with send_taskqueue:
            for board in iterable:
                await send_taskqueue.send(board)
                n += 1
                if n & 0x3F == 0:
                    print(f"\rtaskqueued {n} requests", end='')


    # Not sure if this serves any actual purpose compared to the simpler `mass_queue`.
    # Need to run an actual memory usage comparison
    async def mass_queue_set(self, all_positions:set):
        '''
        Pretty much what the interface suggests. Given a set of positions (FEN strings), queue them all into the DB as
        fast as possible. Better hope you don't get rate limited lol

        Note: consumes the given set, upon return the set should be empty
        '''
        u = len(all_positions)
        print(f"now mass queueing {u} positions")
        await self.mass_request(self.queue, self._set_reader, all_positions)
        print(f"\nall {u} positions have been queued for analysis")

    @staticmethod
    async def _set_reader(send_taskqueue:trio.MemorySendChannel, fenset):
        n = 0
        async with send_taskqueue:
            while fenset: # maybe popping will free memory on the fly? otherwise should just use forloop... TODO
                await send_taskqueue.send(chess.Board(fenset.pop()))
                n += 1
                if n & 0x3F == 0:
                    print(f"\rtaskqueued {n} requests", end='')

    #
    ####################################################################################################################
    ####################################################################################################################
    # Next we have some fancier stuff built atop `self.mass_request`. These next examples use `BreadthFirstState` to
    # generate what work is to be done.

    async def query_breadth_first(self, bfs:BreadthFirstState, maxply=math.inf, count=math.inf):
        '''
        Query CDB positions in breadth-first order, using the given BreadthFirstState. Returns a list of the API's
        json output.
        '''
        return await self.mass_request(self.query_all,
                                       self._breadth_first_producer, bfs, maxply, count,
                                       collect_results=True)

    @staticmethod
    async def _breadth_first_producer(send_taskqueue:trio.MemorySendChannel,
                                      bfs:BreadthFirstState, maxply=math.inf, count=math.inf):
        async with send_taskqueue:
            for board in bfs.iter_resume(maxply, count):
                await send_taskqueue.send(board)


    async def query_bfs_filter_simple(self, pos:chess.Board, predicate, filter_count, maxply=math.inf, count=math.inf,
                                                                                      batchsize=None):
        '''
        Given a `predicate`, which is a function on (chess.Board, CDB's json data for that board) returning a bool,
        search for `filter_count` positions which pass the filter, using mass queries of size `batchsize`. Returns a list
        of such positions found. `batchsize` should be a multiple of `self.concurrency` for efficient use (default 16x).
        '''
        # TODO: this is a synchronous function lol
        if not batchsize:
            batchsize = 16 * self.concurrency
        bfs = BreadthFirstState(pos)
        # TODO: could yield each batch's results as it goes, to enable writing to file inbetween each batch, which
        # would allow interuppting a too-long search
        found = []
        print(f"starting bfs filter search, limits: {maxply=} {count=}, target positions = {filter_count} ({batchsize=})")
        n = 0
        while n < count and len(found) < filter_count and bfs.relative_ply() <= maxply:
            print(f"found {len(found)} from {n} queries, querying next batch...")
            results = await self.query_breadth_first(bfs, maxply, count=batchsize)
            n += len(results)
            for board, response in results:
                if response['status'] is CDBStatus.Success and predicate(board, response):
                    found.append((board, response))
        print(f"after {n} queries, found {len(found)} positions passing the predicate")
        return found

    # TODO: implement the "smart" bfs_filter using CircularRequesters (now that it's built)?
    #
    ####################################################################################################################
    ####################################################################################################################
    # This section deals with CircularRequesters and uses thereof. Unlike the `mass_request` family, where each request
    # is independent, CircularRequesters sets up the `trio` utilities necessary for completed requests to feedback into
    # and guide future requests. The most obvious use of this is where we traverse CDB "near PVs", where each new node
    # generates subsequent requests depending on whatever moves CDB returns. Probably many other uses of this sort of
    # progressive requesting is possible, but nobody's yet conceived of them... the world is your oyster!

    async def iterate_near_pv(self, rootboard:chess.Board, visitor, cp_margin, *, margin_decay=1.0, maxbranch=math.inf,
                                                                                  maxply=math.inf) -> dict:
        '''
        Iterates "near" the PVs of a given `rootboard`, where "near" is defined as `thisscore >= bestscore - cp_margin`.
        (Note that the rootboard's score is irrelevant, only the current node's bestscore, less the margin, is compared
        against the current node's nonbest scores.) Iteration terminates upon hitting leaf nodes (e.g.
        CDBStatus.UnknownBoard, CDBStatus.TrivialBoard), which includes nodes with "solved" decisive scores (> 19000).

        Such iteration is done by means of recursive `query_all` calls, in a more or less breadth-first order, altho
        with low branching factors the resulting tree can look rather like an MCTS tree with high selective depths.

        Upon seeing a fresh node, before iterating into its near-best children, this calls the `visitor` so that the user
        may take some custom action for themself. For example, the `visitor` may also issue a `queue` on the node (in
        addition to the `query_all` that produced the node), or the `visitor` may apply some custom filtering of its own
        for later return to the user. Indeed, the `visitor`'s return value is stored in a dict with structure
        `{fenstr: visitor_retval}`, this dict being the return value of this function.

        `visitor` must be a callable with the following signature:
        async def visitor(client:AsyncCDBClient, circular_requesters:CircularRequesters,
                          board:chess.Board, result, margin, relply, maxply) -> retval | None:
        The visitor may make (arbitrary) api calls by e.g. `circular_requesters.make_request(client.queue, (board,))`.
        `iterate_near_pv` will ignore any api calls made by the visitor. The visitor should not use query_all (as the
        iterator will do so), but any other api call is fair game.
        `board` is the current node; amongst other things, this contains the fen and the moves used to reach this node
        `result` is whatever was returned by `client.query_all(board)`.
        `margin` is whatever the local margin at this node is that iterate_near_pv is using.
        `relply` is the relative ply from the root of this `board`.
        `maxply` is the maximum ply which the iterator will stop searching at.
        (The included visitor `iterate_near_pv_visitor_queue_any` ignores the last two arguments.)
        See the `near_pv*` family of scripts included next to this package to see some example visitors.

        The keyword args customize the margin-iteration behavior for various purposes.
        `margin_decay` is a positive number which linearly shrinks the margin at a rate of `margin_decay` per ply.
            For example, `cp_margin` of 20 and `margin_decay` of 1 would result in relply=10 having cp_margin=10 and
                relply 20 and higher having cp_margin=0.
            This is useful to aid exploration near root without exploding the search too much when far from the root.
        `maxbranch` is an integer which caps the maximum branching at any given node, regardless of other limits.
        `maxply` is an interger which caps the maximum relative ply to search from the root.

        Typically merely one of decay or maxbranch is needed to control fortresses/explosions, but mileage will vary.

        TODO:
        `fortress_detection`
        '''
        if cp_margin > 200: # TODO: is this too low? am i too paranoid?
            raise ValueError(f"{cp_margin=} is too high, and would make a lot of bad requests")
        if maxbranch < 0:
            raise ValueError(f"{maxbranch=} must be zero or positive")

        all_results = {} # get that yucky global feeling again
        s = qa = d = todo = seldepth = 0 # todo = queryalls sent but unprocessed, qa = qas processed,
        # s = nonleaf nodes ("stem") (possibly excluding root), d = duplicate hits
        baseply = rootboard.ply()

        # Not thread safe to refer to variables outside the nursery scope (so to speak)
        try: # Recycle this indentation level...
          async with trio.open_nursery() as nursery:
            circular_requesters = CircularRequesters(self, nursery) # Amongst other duties, deduplicating transpositions
            # is delegated to the requesters.
            await circular_requesters.make_request(self.query_all, (rootboard,))
            todo += 1
            print(f"spawned requesters and sent first query_all for {rootboard.fen()}")

            # Now we act as the "producer", processing request results and sending more requests
            with circular_requesters.as_with(): # save some indent here
              while await circular_requesters.check_circular_busy():
                api_call, args, result = await circular_requesters.read_response()
                #print("processing result:", api_call.__name__, board.safe_peek(), board.fen())
                # any calls other than query_all aren't our business, so to speak, and are ignored.
                if api_call != self.query_all: # https://stackoverflow.com/a/15977850
                    continue

                #print("processing queryall result")
                qa += 1; todo -= 1;
                board = args[0]
                # we want the ply counters to include leaves, tho we only print on nonleaves (or transposing "leaves")
                relply = board.ply() - baseply
                seldepth = max(relply, seldepth)
                margin = max(round(cp_margin - margin_decay * relply), 0)
                #print('\n', f"{relply=}, {cp_margin=}, {margin_decay=}, {margin=}")

                # result may still be json or a CDBStatus, give the visitor a chance to act on that
                vres = await visitor(self, circular_requesters, board, result, margin, relply, maxply)
                if vres: # len(all_results) is at least s but also includes "leaves" which have only transposing children
                    all_results[strip_fen(board.fen())] = vres # board.fen() remains monumentally expensive

                # having given the visitor its chance, now we iterate
                if result['status'] is not CDBStatus.Success or relply >= maxply:
                    continue
                moves = result['moves']
                score = moves[0]['score']
                if abs(score) > 19000:
                    return

                score_margin = score - margin
                # One catch: a now-nonleaf may turn out to have entirely transposing children, which makes it a leaf
                new_children = 0
                for i, move in enumerate(moves):
                    if i >= maxbranch or move['score'] < score_margin:
                        break
                    child = board.copy(stack=True)
                    child.push_uci(move['uci'])
                    #print(f"iterating into {move['san']}")
                    unique = await circular_requesters.make_request(self.query_all, (child,))
                    if unique:
                        new_children += 1
                    else:
                        d += 1
                if not new_children:
                    continue # no printing for you, transposing node!
                todo += new_children
                s += 1
                _s = s + (qa <= 1) # for branching factor we divide by nonleaves, but if root is a leaf then that would be 0/0
                print(f"\rnodes={qa} stems={s} ply={relply} {margin=} {score=} br={new_children}"
                      f" brf={(qa-1+todo)/_s:.2f} dups={d} {todo=} t/n={todo/qa:.2%}:"
                      f" \t  moves={len(moves)}:" # {board.fen()}
                      f''' {", ".join(f"{move['san']}={move['score']}" for move in moves[:3]):<8}    ''', end='')
            # end circular requesters
        # end nursery
        except KeyboardInterrupt:
            print("\ninterrupted, exiting")
        except:
            print(traceback.format_exc())
            raise
        finally:
            rs, rp = circular_requesters.stats()
            _s = s + (qa <= 1) # for branching factor we divide by nonleaves, but if root is a leaf then that would be 0/0
            print(f"\nfinished. sent {rs} requests, processed {rp}.\n"
                  f"{qa} nodes, {s} nonleaves, {todo} skipped (branching factor {(qa-1+todo)/_s:.2f}), "
                  f"duplicates {d}, seldepth {seldepth}.\nthe visitor returned {len(all_results)} results.")
            return all_results

# end class AsyncCDBLibrary
########################################################################################################################
########################################################################################################################



########################################################################################################################

def parse_pgn_to_set(filehandle, start=0, count=math.inf):
    '''
    Read one PGN file: load any and all positions found in the file into memory, including all PVs in comments.
    Deduplicate, returning a set of FENs. With large files, can cause large memory consumption.

    The PGN parser is so tolerant to malformed data that detecting it is difficult. Thus, malformed data may cause
    difficult-to-trace downstream errors.

    Users pass a `filehandle`, whose management is the user's problem. Skip `start` games from the file, then read
    no more than `count`.

    returns (set of unique-ified parsed postions, count of pre-dedup positions seen)
    '''
    print(f"reading '{filehandle.name}' ...")

    if start > 0:
        print(f"skipping {start} games")
    _start = start
    while _start > 0 and (game := chess.pgn.read_game(filehandle, Visitor=chess.pgn.SkipVisitor)) is not None:
        _start -= 1
        #print(f"skipped a game, {_start} to go")
    if _start > 0:
        print(f"still need to skip {_start} games but no more in the file")
        return set(), 0

    games = []
    n = 0
    while n < count and (game := chess.pgn.read_game(filehandle)) is not None:
        games.append(game)
        n += 1
    if n < count < math.inf:
        print(f"read only {n} games instead of {count} from {filehandle.name}")
    else:
        print(f"read {n} games from {filehandle.name}")
    # no real way to validate the parsed data, just assume it's good and hope for the best

    all_positions = set()
    x = 0
    for i, game in enumerate(games, start=start+1):
        n = m = 0
        #print(f"processing game {i}")
        for node in game.all_variations():
            parent = node.parent
            if parent:
                pboard = node.parent.board() # TODO: ChildNode.board() is very, very expensive, refactor?
                board = pboard.copy(stack=False)
                board.push(node.move)
                #print(f"just added node {m}, reached by {pboard.san(node.move)}, now checking comment for pv...")
            else:
                board = node.board()
                pboard = None
            all_positions.add(strip_fen(board.fen()))
            n += 1
            m += 1

            if pboard:
                comment_pv_sans = node.parse_comment_pv_san()
                if comment_pv_sans:
                    n += len(comment_pv_sans)
                    #print(f"found comment pv at board:\n{board}\nadding {len(comment_pv_sans)} positions")
                    # generally, the first move of pv is the same as the played move, but rarely not
                    #if comment_pv_sans[0] != node.san():
                    #    print(f"game {i}, ply {board.ply()}: found node where move played differs from pv! {node.san()} vs {comment_pv_sans[0]} ")
                    for fen in pboard.yield_fens_from_sans(comment_pv_sans):
                        all_positions.add(strip_fen(fen))
        print(f"in game {i} found {m} nodes, {n} positions")
        x += n
    unique = len(all_positions)
    print(f"after deduplicating {filehandle.name}, found {unique} unique positions "
          f"from {x} total, {unique/x:.2%} unique rate")
    return all_positions, x # hopefully all the other crap here is garbage-collected quickly, freeing memory


