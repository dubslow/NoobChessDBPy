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

__all__ = ['BreadthFirstState', 'AsyncCDBLibrary']

'''This file implements some standard CDB interaction algorithms, building atop the API.
Arguments may be either `chess` objects or strings, altho work TBD to handle strings'''

import chess
import chess.pgn
import trio
from .api import AsyncCDBClient, CDBStatus
from . import chess_extensions
import math
from collections import deque
from pprint import pprint

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
        self.rootpos = rootpos
        self.board = rootpos.copy(stack=False)
        self.queue = deque(self.board.legal_child_boards())

    def iter_resume(self, maxply=math.inf, count=math.inf):
        _sanitize_int_limit(maxply)
        _sanitize_int_limit(count)
        n = 0

        self.board = self.queue.popleft() # still need a do...while syntax!
        print(f"starting bfs iter at {self.board.ply()=} with {count=} {maxply=}")
        while self.board.ply() <= maxply and n < count:
            n += 1
            yield self.board
            self.queue.extend(self.board.legal_child_boards(stack=False))
            # In unlimited mode, the queue is on average "fucking big"
            self.board = self.queue.popleft()
            #print(f"asdf {n=} {self.board.ply()=}, {maxply=}")

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

    async def query_bfs_filter_simple(self, pos:chess.Board, predicate, filter_count, chunksize=2048):
        '''
        Given a `predicate`, which is a function on (chess.Board, CDB's json data for that board) returning a bool,
        search for `filter_count` positions which pass the filter, using mass queries of size `chunksize`. Returns a list
        of such positions found.
        '''
        # TODO: could yield each chunk's results as it goes, to enable writing to file in between each chunk, which
        # allow interuppting a too-long search
        found = []
        bfs = BreadthFirstState(pos)
        print(f"starting bfs filter search for {filter_count} positions, {chunksize=}")
        n = 0
        while len(found) < filter_count:
            print(f"found {len(found)} from {n} queries, querying next chunk...")
            results = await self.query_breadth_first(bfs, count=chunksize)
            for board, response in results:
                if not isinstance(response, CDBStatus) and predicate(board, response):
                    found.append((board, response))
            n += chunksize
        print(f"after {n} queries, found {len(found)} positions passing the predicate")
        return found

    ####################################################################################################################

    # Reimplementing the query_b_f code is... quite the burden, and it would be considerably simpler to loop over that
    # with the filter, but estimating the looping involved is tricky and perhaps involves overshoot. Whereas this format
    # enables more accurate estimation (and less overshoot) of queries needed to reach `filtercount` positions.
    async def query_bfs_filter_smart(self, bfs:BreadthFirstState, filter, filtercount):
        print(f"{self.concurrency=} {count=}")
        async with trio.open_nursery() as nursery:
            nursery.done = trio.Event()
            # hack: we use this as a counter, without having to separately store a lock and variable
            nursery.count = trio.Sempahore()  # release = increment lol

            # in general, we use the "tasks close their channel" pattern
            #send_bfs, recv_bfs = trio.open_memory_channel(self.concurrency)
            #nursery.start_soon(self._query_breadth_filter_producer, send_bfs, bfs, maxply, count)

            results = []
            #send_serialize, recv_serialize = trio.open_memory_channel(self.concurrency)
            #nursery.start_soon(self._serializer, recv_serialize, results)

            #async with recv_bfs, send_serialize:
            #    for i in range(self.concurrency):
                    #nursery.start_soon(self._query_breadth_filter_consumer, recv_bfs.clone(), send_serialize.clone())


        return results

    async def _query_breadth_filter_consumer(self, recv_bfs:trio.MemoryReceiveChannel,
                                                  send_serialize:trio.MemorySendChannel):
        async with recv_bfs, send_serialize:
            async for board in recv_bfs:
                await send_serialize.send(await self.query_all(board))

    async def _query_breadth_filter_producer(self, send_bfs:trio.MemorySendChannel, bfs:BreadthFirstState,
                                                  maxply=math.inf, count=math.inf):
        async with send_bfs:
            for board in bfs.iter_resume(maxply, count):
                await send_bfs.send(board)

    ####################################################################################################################

    @staticmethod
    def parse_pgn(filehandle, start=0, count=math.inf) -> set[str]:
        '''
        Read one PGN file: load any and all positions found in the file into memory and deduplicate, returning a set of
        FENs. With large files, can cause large memory consumption.

        The PGN parser is so tolerant to malformed data that detecting it is difficult. Thus, malformed data may cause
        difficult-to-trace downstream errors.

        Skip `start` games from the file, then read no more than `count`.
        '''
        print(f"reading {filehandle.name}...")

        if start > 0:
            print(f"skipping {start} games")
        _start = start
        while _start > 0 and (game := chess.pgn.read_game(filehandle, Visitor=chess.pgn.SkipVisitor)) is not None:
            _start -= 1
            #print(f"skipped a game, {_start} to go")
        if _start > 0:
            print(f"still need to skip {_start} games but no more in the file")
            return set()

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

        all_positions = set() # read entire file and de-duplicate before sending queue requests
        x = 0
        for i, game in enumerate(games, start=start+1):
            n, m = 0, 0
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
                        for fen in pboard.yield_fens_from_sans(comment_pv_sans):
                            all_positions.add(fen)
            print(f"in game {i} found {m} nodes, {n} positions")
            x += n
        unique = len(all_positions)
        print(f"after deduplication, found {unique} unique positions from {x} total, {unique/x:.2%} unique rate")
        return all_positions # hopefully all the other crap here is garbage-collected quickly, freeing memory


    async def mass_queue(self, all_positions:set[str]):
        '''
        Pretty much what the interface suggests. Given a collection of positions, queue them all into the DB as fast as
        possible. Better hope you don't get rate limited lol

        Note: consumes the given set, upon return the set should be empty
        '''
        await self.mass_request(self.queue, self._set_reader, all_positions)

    @staticmethod
    async def _set_reader(send_taskqueue:trio.MemorySendChannel, _set):
        n = 0
        async with send_taskqueue:
            while _set: # maybe popping will free memory on the fly? otherwise should just use forloop... TODO
                await send_taskqueue.send(chess.Board(fen=_set.pop()))
                n += 1
                if n & 0x7FF == 0:
                    print(f"taskqueued {n} requests")


