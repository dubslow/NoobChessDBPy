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
    '''Recursively iterate over the `board`'s legal moves, excluding the `board` itself,
    subject to ply <= `maxply` (min 1). Order of moves in a given position is arbitrary,
    whatever `chess.Board` does. `maxply` compares directly against `rootpos.ply()`.'''
    def __init__(self, rootpos:chess.Board):
        self.rootpos = rootpos
        self.board = rootpos.copy(stack=False)
        self.queue = deque(self.board.legal_child_boards())

    def iter_resume(self, maxply=math.inf, count=math.inf):
        # _copystack=False disables maxply in exchange for speed
        _sanitize_int_limit(maxply)
        _sanitize_int_limit(count)
        n = 0

        self.board = self.queue.popleft() # still need a do...while syntax!
        print(f"ASDF {self.board.ply()=}, {maxply=}")
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

    @staticmethod
    async def _serializer(recv_serialize, collector):
        # in theory, we shouldn't need the collector arg, instead making our own and returning it to the nursery...
        async with recv_serialize:
            async for val in recv_serialize:
                collector.append(val)


    async def query_breadth_first(self, bfs:BreadthFirstState, concurrency=256, maxply=math.inf, count=math.inf):
        '''Query CDB positions in breadth-first order, using the given BreadthFirstState. Returns a list of the API's
        json output.'''
        print(f"{concurrency=} {count=}")
        async with trio.open_nursery() as nursery:
            # in general, we use the "tasks close their channel" pattern
            send_bfs, recv_bfs = trio.open_memory_channel(concurrency)
            nursery.start_soon(self._query_breadth_first_producer, send_bfs, bfs, maxply, count)

            results = []
            send_serialize, recv_serialize = trio.open_memory_channel(concurrency)
            nursery.start_soon(self._serializer, recv_serialize, results)

            async with recv_bfs, send_serialize:
                for i in range(concurrency):
                    nursery.start_soon(self._query_breadth_first_consumer, recv_bfs.clone(), send_serialize.clone())

        return results

    async def _query_breadth_first_consumer(self, recv_bfs:trio.MemoryReceiveChannel,
                                                  send_serialize:trio.MemorySendChannel):
        async with recv_bfs, send_serialize:
            async for board in recv_bfs:
                await send_serialize.send(await self.query_all(board))

    async def _query_breadth_first_producer(self, send_bfs:trio.MemorySendChannel, bfs:BreadthFirstState,
                                                  maxply=math.inf, count=math.inf):
        async with send_bfs:
            for board in bfs.iter_resume(maxply, count):
                await send_bfs.send(board)

    # Reimplementing the query_b_f code is... quite the burden, and it would be considerably simpler to loop over that
    # with the filter, but estimating the looping involved is tricky and perhaps involves overshoot. Whereas this format
    # enables more accurate estimation (and less overshoot) of queries needed to reach `filtercount` positions.
    async def query_breadth_first_filter(self, bfs:BreadthFirstState, filter, filtercount, concurrency=256):
        print(f"{concurrency=} {count=}")
        async with trio.open_nursery() as nursery:
            nursery.done = trio.Event()
            # hack: we use this as a counter, without having to separately store a lock and variable
            nursery.count = trio.Sempahore()  # release = increment lol

            # in general, we use the "tasks close their channel" pattern
            send_bfs, recv_bfs = trio.open_memory_channel(concurrency)
            nursery.start_soon(self._query_breadth_filter_producer, send_bfs, bfs, maxply, count)

            results = []
            send_serialize, recv_serialize = trio.open_memory_channel(concurrency)
            nursery.start_soon(self._serializer, recv_serialize, results)

            async with recv_bfs, send_serialize:
                for i in range(concurrency):
                    nursery.start_soon(self._query_breadth_filter_consumer, recv_bfs.clone(), send_serialize.clone())

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



