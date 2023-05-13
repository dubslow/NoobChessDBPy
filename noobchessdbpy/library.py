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

__all__ = ['BreadthFirstState', 'AsyncCDBLibrary']

########################################################################################################################

from collections import deque
import math
from typing import Iterable

import chess
import chess.pgn
import trio

from .api import AsyncCDBClient, CDBStatus
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
                if self.n & 0x7FF == 0: print(f"bfs: {self.n=} relative ply {self.board.ply() - self.rootply}") #{self.d=} {self.d/self.n=:.2%}")
                self.seen.add(self.fen)
                yield self.board
            else:
                self.d += 1
            self.fen = self.queue.popleft()
            self.board = chess.Board(self.fen)
        print(f"finished bfs iter at {n=}, relative ply {self.board.ply() - self.rootply}")

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
        await self.mass_request(self.queue, self._iterable_reader, all_positions)

    @staticmethod
    async def _iterable_reader(send_taskqueue:trio.MemorySendChannel, iterable):
        n = 0
        async with send_taskqueue:
            for board in iterable:
                await send_taskqueue.send(board)
                n += 1
                if n & 0x7FF == 0:
                    print(f"taskqueued {n} requests")

    async def mass_queue_set(self, all_positions:set[str]):
        '''
        Pretty much what the interface suggests. Given a set of positions (FEN strings), queue them all into the DB as
        fast as possible. Better hope you don't get rate limited lol

        Note: consumes the given set, upon return the set should be empty
        '''
        await self.mass_request(self.queue, self._set_reader, all_positions)

    @staticmethod
    async def _set_reader(send_taskqueue:trio.MemorySendChannel, fenset):
        n = 0
        async with send_taskqueue:
            while fenset: # maybe popping will free memory on the fly? otherwise should just use forloop... TODO
                await send_taskqueue.send(chess.Board(fenset.pop()))
                n += 1
                if n & 0x7FF == 0:
                    print(f"taskqueued {n} requests")


