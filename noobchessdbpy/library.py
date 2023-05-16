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
API client: `AsyncCDBLibrary`. Create an instance of this class to use the algorithms.

Arguments are generally `chess` objects.
'''

__all__ = ['BreadthFirstState', 'AsyncCDBLibrary', 'CircularRequesters']

########################################################################################################################

from collections import deque
from contextlib import contextmanager
import math
from typing import Iterable

import chess
import chess.pgn
import trio
from trio.lowlevel import checkpoint

from .api import AsyncCDBClient, CDBStatus, _strip_fen
from . import chess_extensions

########################################################################################################################

def _sanitize_int_limit(n):
    if n is None or n < 1:
        raise ValueError(f"limit must be at least 1 (got {n})")

########################################################################################################################

class BreadthFirstState:
    '''
    Recursively iterate over the `board`'s legal moves, excluding the `board` itself, subject to ply <= `maxply` (min 1).
    Order of moves in a given position is arbitrary, whatever `chess.Board` does. `maxply` compares directly against
    `rootpos.ply()`.

    `__init__` arg is the base position; state is remembered between each `iter_resume` call.
    '''
    def __init__(self, rootpos:chess.Board):
        self.rootpos = rootpos.copy()
        self.rootply = self.rootpos.ply()

        self.queue = deque(rootpos.legal_child_fens())
        self.seen = set()
        self.n = self.d = 0
        # if we've yielded `n` positions, and our tree has branching factor `b`, then on average the memory use is about
        # `queue`: sizeof(chess.Board) * n * b (b ~ 35-40, so this is a lot)
        #  `seen`: sizeof(fenstr) * n
        self.fen = self.queue.popleft()
        self.board = chess.Board(self.fen)

    def iter_resume(self, maxply=math.inf, count=math.inf):
        _sanitize_int_limit(maxply)
        _sanitize_int_limit(count)
        n = 0

        print(f"starting bfs iter at relative ply {self.board.ply() - self.rootply} with {count=} {maxply=}")
        while n < count and (self.board.ply() - self.rootply) <= maxply:
            if self.fen not in self.seen:
                n += 1; self.n += 1
                # In unlimited mode, the queue is on average "fucking big"
                # surprisingly (to me at least), pre-filtering for duplicates here doesn't do much of anything
                # altho even a little something might be a benefit when 1M nodes deep
                self.queue.extend(filter(lambda f: f not in self.seen, self.board.legal_child_fens(stack=False)))
                if self.n & 0x3F == 0: print(f"bfs: {self.n=} relative ply {self.board.ply() - self.rootply}", end='\r') #{self.d=} {self.d/self.n=:.2%}")
                self.seen.add(self.fen)
                yield self.board
            else:
                self.d += 1
            self.fen = self.queue.popleft()
            self.board = chess.Board(self.fen)
        print(f"\nfinished bfs iter at {n=}, relative ply {self.board.ply() - self.rootply}")

    def relative_ply(self):
        return self.board.ply() - self.rootply

########################################################################################################################

class AsyncCDBLibrary(AsyncCDBClient):
    '''In general, we try to reuse a single client as much as possible, so algorithms are implemented
    as a subclass of the client.'''

    # Maybe we can later export static variations which construct a new client on each call?
    def __init__(self, **kwargs):
        '''This AsyncCDBClient subclass may be initialized with any kwargs of the parent class'''
        super().__init__(**kwargs)

    ####################################################################################################################

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

    ####################################################################################################################

    async def query_fens(self, fens:Iterable[str]):
        '''
        Very basic: given a container of FENs, query them all and return the CDB results. Can be used for arbitrarily
        large containers, so long as you don't hit the rate limit.
        '''
        # Note: for containers of size less than the concurrency, this can be quite wasteful. Alas, nurseries not returning
        # retvals by default makes it tougher...
        return await self.mass_request(self.query_all, self._query_fen_producer, fens, collect_results=True)

    @staticmethod
    async def _query_fen_producer(send_taskqueue:trio.MemorySendChannel, fens:Iterable[str]):
        async with send_taskqueue:
            for fen in fens:
                await send_taskqueue.send(chess.Board(fen))

    ####################################################################################################################

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

    ####################################################################################################################

    async def query_bfs_filter_simple(self, pos:chess.Board, predicate, filter_count, maxply=math.inf, count=math.inf, batchsize=None):
        '''
        Given a `predicate`, which is a function on (chess.Board, CDB's json data for that board) returning a bool,
        search for `filter_count` positions which pass the filter, using mass queries of size `batchsize`. Returns a list
        of such positions found. `batchsize` should be a multiple of `self.concurrency` for efficient use (default 16x).
        '''
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
                if not isinstance(response, CDBStatus) and predicate(board, response):
                    found.append((board, response))
        print(f"after {n} queries, found {len(found)} positions passing the predicate")
        return found

    ####################################################################################################################

    # Reimplementing the query_b_f code is... quite the burden, and it would be considerably simpler to loop over that
    # with the filter, but estimating the looping involved is tricky and perhaps involves overshoot. Whereas this format
    # enables more accurate estimation (and less overshoot) of queries needed to reach `filtercount` positions.
    #async def query_bfs_filter_smart(self, bfs:BreadthFirstState, filter, filtercount):
    #    print(f"{self.concurrency=} {count=}")
    #    async with trio.open_nursery() as nursery:
    #        nursery.done = trio.Event()
    #        # hack: we use this as a counter, without having to separately store a lock and variable
    #        nursery.count = trio.Sempahore()  # release = increment lol
    #
    #        # in general, we use the "tasks close their channel" pattern
    #        #send_bfs, recv_bfs = trio.open_memory_channel(self.concurrency)
    #        #nursery.start_soon(self._query_breadth_filter_producer, send_bfs, bfs, maxply, count)
    #
    #        results = []
    #        #send_serialize, recv_serialize = trio.open_memory_channel(self.concurrency)
    #        #nursery.start_soon(self._serializer, recv_serialize, results)
    #
    #        #async with recv_bfs, send_serialize:
    #        #    for i in range(self.concurrency):
    #                #nursery.start_soon(self._query_breadth_filter_consumer, recv_bfs.clone(), send_serialize.clone())
    #
    #
    #    return results
    #
    #async def _query_breadth_filter_consumer(self, recv_bfs:trio.MemoryReceiveChannel,
    #                                              send_serialize:trio.MemorySendChannel):
    #    async with recv_bfs, send_serialize:
    #        async for board in recv_bfs:
    #            await send_serialize.send(await self.query_all(board))
    #
    #async def _query_breadth_filter_producer(self, send_bfs:trio.MemorySendChannel, bfs:BreadthFirstState,
    #                                              maxply=math.inf, count=math.inf):
    #    async with send_bfs:
    #        for board in bfs.iter_resume(maxply, count):
    #            await send_bfs.send(board)

    ####################################################################################################################

    @staticmethod
    def parse_pgn(filehandle, start=0, count=math.inf) -> (set[str], int):
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
                all_positions.add(board.fen())
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
                            all_positions.add(fen)
            print(f"in game {i} found {m} nodes, {n} positions")
            x += n
        unique = len(all_positions)
        print(f"after deduplicating {filehandle.name}, found {unique} unique positions "
              f"from {x} total, {unique/x:.2%} unique rate")
        return all_positions, x # hopefully all the other crap here is garbage-collected quickly, freeing memory

    ####################################################################################################################

    async def mass_queue(self, all_positions:Iterable[chess.Board]):
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
                    print(f"taskqueued {n} requests", end='\r')

    async def mass_queue_set(self, all_positions:set[str]):
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
                    print(f"taskqueued {n} requests", end='\r')

    ####################################################################################################################

    async def cdb_iterate(self, rootboard:chess.Board, visitor, cp_margin=5) -> dict:
        '''
        Iterates "near" the PVs of a given `rootboard`, where "near" is defined as `thisscore >= bestscore - cp_margin`.
        (Note that the rootboard's score is irrelevant, only the current node's bestscore, less the margin, is compared
        against the current node's nonbest scores.) Iteration terminates upon hitting leaf nodes (e.g.
        CDBStatus.UnknownBoard, CDBStatus.TrivialBoard), including leaves with "solved" decisive scores (> 19000).

        Such iteration is done by means of recursive `query_all` calls, in a more or less breadth-first order, altho
        with low branching factors the resulting tree can look rather like an MCTS tree with high selective depths.

        Upon seeing a fresh node, before iterating into its near-best children, this calls the `visitor` so that the user
        may take some custom action for themself. For example, the `visitor` may also issue a `queue` on the node (in
        addition to the `query_all` that produced the node), or the `visitor` may apply some custom filtering of its own
        for later return to the user. Indeed, the `visitor`'s return value is stored in a dict with structure
        `{fenstr: visitor_retval}`, this dict being the return value of this function.

        `visitor` must be a callable with the following signature:
        async def visitor(client:AsyncCDBClient, circular_requesters:CircularRequesters, board:chess.Board, result, cp_margin) -> retval | None
        The visitor may make (arbitrary) api calls by e.g. `circular_requesters.make_request(client.queue, (board,))`.
        `result` is whatever was returned by `client.query_all(board)`.
        '''
        if cp_margin > 200: # TODO: is this too low? am i too paranoid?
            raise ValueError(f"{cp_margin=} is too high, and would make a lot of bad requests")
        all_results = {} # get that yucky global feeling again
        s = qa = d = todo = maxply = 0 # todo = queryalls sent but unprocessed, qa = qas processed,
        # s = nonleaf nodes ("stem") (possibly excluding root), d = duplicate hits
        baseply = rootboard.ply()

        # Not thread safe to refer to variables outside the nursery scope (so to speak)
        try:
         async with trio.open_nursery() as nursery:
            circular_requesters = CircularRequesters(self, nursery) # Amongst other duties, deduplicating transpositions
            # is delegated to the requesters.
            await circular_requesters.make_request(self.query_all, (rootboard,))
            todo += 1
            print(f"spawned requesters and sent first query_all for {rootboard.fen()}")

            # Now we act as the "producer", processing request results and sending more requests, loop control TBD
            with circular_requesters.as_with():
                while not await circular_requesters.check_circular_idle():
                    #print("hah...", (stats := self.recv_request.statistics()).tasks_waiting_receive, stats.open_receive_channels, self.recv_results.statistics().current_buffer_used)
                    api_call, args, result = await circular_requesters.read_response()
                    board = args[0]
                    #print("processing result:", api_call.__name__, board.safe_peek(), board.fen())
                    # any calls other than query_all aren't our business, so to speak, and are ignored.
                    if api_call != self.query_all: # https://stackoverflow.com/a/15977850
                        continue
                    #print("processing queryall result")
                    qa += 1; todo -= 1
                    # we want the ply counters to include leaves, tho we only print on nonleaves
                    relply = board.ply() - baseply
                    maxply = max(relply, maxply)

                    # result may still be json or a CDBStatus, give the visitor a chance to act on that
                    vres = await visitor(self, circular_requesters, board, result)
                    if vres:
                        all_results[board.fen()] = vres # board.fen() remains monumentally expensive
                    if not isinstance(result, dict):
                        continue

                    # having given the visitor its chance, now we iterate
                    moves = result['moves']
                    score = moves[0]['score']
                    if abs(score) > 19000:
                        return
                    score_margin = score - cp_margin
                    # One catch: a now-nonleaf may turn out to have entirely transposing children, which makes it a leaf
                    new_children = 0
                    for move in moves:
                        if move['score'] >= score_margin:
                            child = board.copy(stack=True)
                            child.push_uci(move['uci'])
                            #print(f"iterating into {move['san']}")
                            unique = await circular_requesters.make_request(self.query_all, (child,))
                            if unique:
                                new_children += 1
                            else:
                                d += 1
                        else:
                            break
                    if new_children:
                        todo += new_children
                        s += 1
                    print(f"\rnodes={qa} stems={s} {relply=} {score=} dups={d} {todo=}: \t   {len(moves)=} " # {board.fen()}
                          f'''{", ".join(f"{move['san']}={move['score']}" for move in moves[:5]):<40}''', end='')
        except KeyboardInterrupt:
            pass
        rs, rp = circular_requesters.stats()
        _s = s + (qa <= 1) # for branching factor we divide by nonleaves, but if root is a leaf then that would be 0/0
        print(f"\nfinished. sent {rs} requests, processed {rp}, {qa} nodes, {s} nonleaves (branching factor {(qa-1+todo)/_s:.2f}), "
              f"duplicates {d}, seldepth {maxply} (cancelled nodes: {todo}). the visitor returned {len(all_results)} results")
        return all_results

    @staticmethod # allow users to write their own visitors, whose first arg is the relevant client instance (TODO?)
    async def cdb_iterate_queue_visitor(self, circular_requesters, board, result):
        '''
        By default, iterate-by-query_all on children within the margin, with an extra queue for good measure if the
        existing moves seem unclear. (But dont iterate into TB/mate scores)
        '''

        if isinstance(result, CDBStatus):
            #print("queryall no results")
            if result not in (CDBStatus.TrivialBoard, CDBStatus.GameOver):
                await circular_requesters.make_request(self.queue, (board,))
            return

        moves = result['moves']
        score = moves[0]['score']
        if abs(score) > 19000:
            return
        #worst_near_margin = moves[-1]['score'] >= (score - min(cp_margin, 50))
        #if len(moves) > 5 and worst_near_margin: # with small margin, this is highly unlikely, but with large margin...
        #    for move in board.legal_moves:
        #        await make_request(self.store, (board, move))
        #else:
        await circular_requesters.make_request(self.queue, (board,))
        return result


class CircularRequesters:
    '''
    Abstract out the setup of a producer guiding requesters, but which also relies on the requester results to make
    further requests. The pattern is useful for e.g. traversing CDB or indeed, say, Wikipedia article links. (6 degrees
    of separation?)

    Must be initialized with an active `AsyncCDBClient` and an active `trio.Nursery`. Performs deduplication upon
    (api_call, args[0]), the latter of which is presumed to be the `chess.Board`. (Implemenation detail: currently only
    deduplicates for `query_all` and `queue`)

    Public methods include `make_request`, `read_response`, `check_circular_idle`, and `stats`.
    '''
    # Circluar memory channels. Determing when we're all done is a bit tricky: it's when all requesters are idle
    # *and* there's no further results for the main task to process.

    def __init__(self, active_client:AsyncCDBClient, active_nursery:trio.Nursery):
        '''
        Must be initialized with an active `AsyncCDBClient` and an active `trio.Nursery`.
        '''
        self.client = active_client
        self.nursery = active_nursery
        self.send_request, self.recv_request = trio.open_memory_channel(self.client.concurrency)
        self.send_results, self.recv_results = trio.open_memory_channel(math.inf) # sigh lol
        # channel data are (api_call, (args*)) or (api_call, (args*), result)
        self.queued_fens, self.queried_fens = set(), set() # gotta be sure to not needlessly double up
        # probably separate sets for queue and query_all is overkill
        self.rs = self.rp = 0

        with self.recv_request, self.send_results: # close the originals to ensure that only channels in use are open
            for i in range(self.client.concurrency):
                self.nursery.start_soon(self._circular_requester, self.recv_request.clone(),
                                                                  self.send_results.clone(), i)

    @contextmanager # It would be desirable to just write `with self:` rather than `with self.as_with():`, but hey
    # see https://stackoverflow.com/a/61471301
    def as_with(self):
        '''
        Use of this method is mandatory to ensure proper cleanup, like so:
        
        ```
        with circular_requesters.as_with():
            while not await circular_requesters.check_circular_idle():
                ...
                send requests and read responses
                ...
        ```

        ...to ensure proper cleanup of the relevant internal resources.
        '''
        with self.send_request, self.recv_results:
            yield

    async def check_circular_idle(self):
        '''
        This *should* be usable in a while loop condition without causing any deadlocking, tho I'm not fully certain
        about that. But at least it's worked in practice so far
        '''
        await checkpoint() # Necessary (sufficient?) for the main task to give way so that the requesters consume any
        # available work. Otherwise, a requester may have finished a request without having yet return the result and
        # gone idle. Even with this checkpoint, I think it only works with "fair scheduling" where the checkpointing
        # task is guaranteed to not resume control until all requesters have gone fully idle. I think...
        # I remain scared that it's possible for this check to fail when it should pass, resulting in infinite blocking
        # in self.read_response().
        #print("looping...", (stats := self.recv_request.statistics()).tasks_waiting_receive, stats.open_receive_channels, self.recv_results.statistics().current_buffer_used)
        stats = self.recv_request.statistics()
        return (    stats.tasks_waiting_receive >= stats.open_receive_channels
                and self.recv_results.statistics().current_buffer_used <= 0)

    async def make_request(self, call, args): # little helper closure
        '''returns if request+board is unique (for `query_all` and `queue`) (the board is assumed to be the first arg)'''
        fen = _strip_fen(args[0].fen())
        if call == self.client.query_all:
            if fen in self.queried_fens:
                return False
            self.queried_fens.add(fen)
        elif call == self.client.queue:
            if fen in self.queued_fens:
                return False
            self.queued_fens.add(fen)
        await self.send_request.send((call, args))
        self.rs += 1
        return True

    async def read_response(self):
        '''read a request's response from the requesters. returns (api_call, args, result)'''
        results = await self.recv_results.receive()
        self.rp += 1
        return results

    def stats(self):
        '''returns (requests sent, requests read)'''
        return self.rs, self.rp

    #@staticmethod
    async def _circular_requester(self, recv_request:trio.MemorySendChannel,
                                  send_results:trio.MemoryReceiveChannel, j=None):
        i=0
        #print(1, send_results._state.open_receive_channels)
        with recv_request, send_results:
            #print(2, send_results._state.open_receive_channels)
            async for api_call, args in recv_request:
                assert api_call.__self__ is self.client # should really, really never fail lol
                #print(f"{j=} {i=} GETting {api_call.__name__}...")
                #print(3, send_results._state.open_receive_channels)
                result = await api_call(*args)
                #print(4, send_results._state.open_receive_channels)
                #print(f"{j=} {i=} GOT {api_call.__name__}, sending result to main task...")
                await send_results.send((api_call, args, result))
                #print(f"{j=} {i=} now idling in for loop")
                i+=1
