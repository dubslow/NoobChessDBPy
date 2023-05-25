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

Since we want to keep reusing one http client, the algorithms are all implemented as methods on a further subclass of
the API client: `AsyncCDBLibrary`. Create an instance of this class to use the algorithms.

Arguments are generally `chess` objects.
'''

from collections import deque
from contextlib import contextmanager
import math

import chess
import trio
from trio.lowlevel import checkpoint

from ..api import AsyncCDBClient, strip_fen

__all__ = ['BreadthFirstState', 'CircularRequesters']

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
        self.seen = set() # for deduplicating, fen should be stripped, however we rely on nonstripped context for maxply
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
            if strip_fen(self.fen) not in self.seen:
                n += 1; self.n += 1
                # In unlimited mode, the queue is on average "fucking big"
                # surprisingly (to me at least), pre-filtering for duplicates here doesn't do much of anything
                # altho even a little something might be a benefit when 1M nodes deep
                self.queue.extend(filter(lambda f: strip_fen(f) not in self.seen,
                                         self.board.legal_child_fens(stack=False)))
                if self.n & 0x3F == 0: print(f"\rbfs: {self.n=} relative ply {self.board.ply() - self.rootply}", end='')
                                             #{self.d=} {self.d/self.n=:.2%}")
                self.seen.add(strip_fen(self.fen))
                yield self.board
            else:
                self.d += 1
            self.fen = self.queue.popleft()
            self.board = chess.Board(self.fen)
        print(f"\nfinished bfs iter at {n=}, relative ply {self.board.ply() - self.rootply}")

    def relative_ply(self):
        return self.board.ply() - self.rootply

########################################################################################################################

class CircularRequesters:
    '''
    Abstract out the setup of a producer guiding requesters, but which also relies on the requester results to produce
    further requests. The pattern is useful for e.g. traversing CDB or indeed, say, Wikipedia article links. (6 degrees
    of separation?)

    Must be initialized with an active `AsyncCDBClient` and an active `trio.Nursery`. Performs deduplication upon
    (api_call, args[0]), the latter of which is presumed to be the `chess.Board`. (Implemenation detail: currently only
    deduplicates for `query_all` and `queue`)

    Public methods include `make_request`, `read_response`, `check_circular_busy`, and `stats`.
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
        send initial request
        with circular_requesters.as_with():
            while await circular_requesters.check_circular_busy():
                ...
                process response
                ...
                send more requests
                ...
        ```

        This ensures proper cleanup of the relevant internal resources.
        '''
        with self.send_request, self.recv_results:
            yield

    async def check_circular_busy(self):
        '''
        Use this to determine if there's still stuff for the main task to process.

        This *should* be usable in a while loop condition without causing any deadlocking, tho I'm not fully certain
        about that. But at least it's worked in practice so far
        '''
        # The basic idea is that we check if requesters are active, or if there're pending results for the main task to
        # process.
        await checkpoint() # The catch is that a requester may have received a response without having yet returned the
        # result to the main task and gone idle. This await is necessary (sufficient?) for the main task to give way so
        # that the requesters come fully idle after receiving a response. However, even with this checkpoint, I think it
        # only works with "fair scheduling" where the checkpointing task is guaranteed to not resume control until all
        # requesters have gone fully idle. I think...
        # I remain scared that it's possible for this check to fail when it should pass, resulting in infinite blocking
        # in self.read_response().
        #print("looping...", (stats := self.recv_request.statistics()).tasks_waiting_receive, stats.open_receive_channels, self.recv_results.statistics().current_buffer_used)
        stats = self.recv_request.statistics()
        return (    stats.tasks_waiting_receive < stats.open_receive_channels # Are there any non-idle requesters?
                or self.recv_results.statistics().current_buffer_used > 0)    # Or else are there pending results?

    async def make_request(self, call, args): # little helper closure
        '''returns if request+board is unique (for `query_all` and `queue`) (the board is assumed to be the first arg)'''
        fen = strip_fen(args[0].fen())
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
        #i=0
        #print(1, send_results._state.open_receive_channels)
        with recv_request, send_results:
            #print(2, send_results._state.open_receive_channels)
            async for api_call, args in recv_request: # The loop wraps recv_request.receive(); idle tasks "block" there
                assert api_call.__self__ is self.client # should really, really never fail lol
                #print(f"{j=} {i=} GETting {api_call.__name__}...")
                #print(3, send_results._state.open_receive_channels)
                result = await api_call(*args)
                #print(4, send_results._state.open_receive_channels)
                #print(f"{j=} {i=} GOT {api_call.__name__}, sending result to main task...")
                await send_results.send((api_call, args, result))
                #print(f"{j=} {i=} now idling in for loop")
                #i+=1

