#! python3.11

'''This file implements some standard CDB interaction algorithms, building atop the API.
Arguments may be either `chess` objects or strings, altho work TBD to handle strings'''

import chess
import chess.pgn
from api import AsyncCDBClient, CDBStatus
import trio
from io import StringIO
from pprint import pprint


class AsyncCDBLibrary(AsyncCDBClient):
    '''In general, we try to reuse a single client as much as possible, so algorithms are implemented
    as a subclass of the client.'''
    # Maybe we can later export static variations which construct a new client on each call?
    def __init__(self, **kwargs):
        '''This AsyncCDBClient subclass may be initialized with any kwargs of the parent class'''
        super().__init__(**kwargs)


    async def analyze_single_line(self, pgn:str):
        '''Given a single line of moves, `queue` for analysis all positions in this line.'''
        game = chess.pgn.read_game(StringIO(pgn))
        # chess.pgn handles variations, and silently we don't actually verify if this pgn has no variations.
        async with trio.open_nursery() as nursery:
            for node in game.mainline():
                nursery.start_soon(self.request_analysis, node.board())


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
                await self.query_all_known_moves(board, learn=0)


