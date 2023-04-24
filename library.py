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


'''This file implements some standard CDB interaction algorithms, building atop the API.
Arguments may be either `chess` objects or strings, altho work TBD to handle strings'''

import chess
import chess.pgn
import trio
from api import AsyncCDBClient, CDBStatus
from io import StringIO
import math
from collections import deque
from pprint import pprint

# Manually extend chess.Board with a couple more utility algorithms:

def legal_child_boards(self, stack=True) -> chess.Board:
    '''A generator over the `legal_moves` of `self`, yielding *copies* of the
    resulting boards. `stack` is the same as for `self.copy`.'''
    for move in self.legal_moves:
        new = self.copy(stack=stack)
        new.push(move)
        yield new

chess.Board.legal_child_boards = legal_child_boards


def _sanitize_int_limit(n):
    if n is None or n < 1:
        raise ValueError(f"limit must be at least 1 (got {n})")

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
            print(f"asdf {n=} {self.board.ply()=}, {maxply=}")


class AsyncCDBLibrary(AsyncCDBClient):
    '''In general, we try to reuse a single client as much as possible, so algorithms are implemented
    as a subclass of the client.'''

    # Maybe we can later export static variations which construct a new client on each call?
    def __init__(self, **kwargs):
        '''This AsyncCDBClient subclass may be initialized with any kwargs of the parent class'''
        super().__init__(**kwargs)


    @staticmethod
    async def _serializer(serialize_recv, collector):
        # in theory, we shouldn't need the collector arg, instead making our own
        # and returning it to the nursery...
        async with serialize_recv:
            async for val in serialize_recv:
                collector.append(val)


    async def queue_single_line(self, pgn:str):
        '''Given a single line of moves, `queue` for analysis all positions in this line.'''
        game = chess.pgn.read_game(StringIO(pgn))
        # chess.pgn handles variations, and silently we don't actually verify if this pgn has no variations.
        async with trio.open_nursery() as nursery:
            for node in game.mainline():
                nursery.start_soon(self.queue, node.board())


    async def query_breadth_first_static(self, rootpos:chess.Board, concurrency=128, maxply=math.inf, count=math.inf):
        bfs = BreadthFirstState(rootpos)
        async with trio.open_nursery() as nursery:
            # about the branching factor should be optimal buffer (tasks close their channel)
            bfs_send, bfs_recv = trio.open_memory_channel(concurrency)
            nursery.start_soon(self._query_breadth_first_producer, bfs_send, bfs, maxply, count)

            results = []
            serialize_send, serialize_recv = trio.open_memory_channel(math.inf)
            nursery.start_soon(self._serializer, serialize_recv, results)

            async with bfs_recv, serialize_send:
                for i in range(concurrency):
                    nursery.start_soon(self._query_breadth_first_consumer, bfs_recv.clone(), serialize_send.clone())

        #return nursery.results
        return results

    async def _query_breadth_first_consumer(self, bfs_recv:trio.MemoryReceiveChannel,
                                                  serialize_send:trio.MemorySendChannel):
        async with bfs_recv, serialize_send:
            async for board in bfs_recv:
                await serialize_send.send(await self.query_all(board))

    async def _query_breadth_first_producer(self, bfs_send:trio.MemorySendChannel,
                                                  state:BreadthFirstState,
                                                  maxply=math.inf, count=math.inf):
        async with bfs_send:
            for board in state.iter_resume(maxply, count):
                await bfs_send.send(board)


    async def breadth_first_speedtest(self, rootpos:chess.Board=None, concurrency=32):
        if rootpos is None:
            rootpos = chess.Board()
            rootpos.push_san('g4') # kekw
        async with trio.open_nursery() as nursery:
            send_channel, recv_channel = trio.open_memory_channel(50) # about the branching factor should be optimal buffer (tasks close their channel)
            for i in range(concurrency):
                nursery.start_soon(self._speedtest_worker, recv_channel.clone())
            nursery.start_soon(self._speedtest_generator, rootpos, concurrency, nursery, send_channel, recv_channel)


    async def _speedtest_generator(self, rootpos, concurrency, nursery, send_channel, recv_channel):
        queue = deque()
        queue.appendleft(rootpos)
        async with send_channel: # always clean up
            await send_channel.send(rootpos) # do while would be nice
            while True:
                curr = queue.pop()
                async for move in curr.legal_moves:
                    new = curr.copy(stack=False)
                    new.push(move)
                    queue.appendleft(new)
                    await send_channel.send(new)
                if send_channel.statistics().tasks_waiting_receive <= 0:
                    increment = concurrency // 4
                    print(f"all {concurrency} workers in use, spawning another {increment}")
                    for i in range(increment):
                        nursery.start_soon(self._speedtest_worker, recv_channel.clone())


    async def _speedtest_worker(self, recv_channel):
        async with recv_channel: # never forget to clean up!
            async for board in recv_channel:
                await self.query_all(board, learn=0)


