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

__all__ = ['CDBStatus', 'CDBError', 'AsyncCDBClient']

'''The python wrapper to the CDB API. In general, create an AsyncCDBClient instance, and use its methods to make API calls.
This class inherits from httpx.AsyncClient, and forwards kwargs.
API call return values are generally json or a CDBStatus value.'''

import trio
import httpx
import chess

from enum import StrEnum, auto
from pprint import pprint

_CDBURL = 'https://www.chessdb.cn/cdb.php'

class CDBStatus(StrEnum):
    '''Enum used for non-moves return values from CDB.
    
    Ok = query served
    Success = normal request and response
    GameOver includes checkmate, stalemate
    UnknownBoard = position not in DB (but maybe now added)
    NoBestMove = position exists, but nevertheless no moves
    TrivialBoard = request for analysis was ignored because trivial position
    LimitExceeded = too many requests from this ipaddr
    '''
    Success       = "ok"
    GameOver      = auto()
    InvalidBoard  = "invalid board"
    UnknownBoard  = "unknown"
    NoBestMove    = "nobestmove"
    TrivialBoard  = ""
    LimitExceeded = "rate limit exceeded"
    LimitCleared  = "rate limit cleared"

class CDBError(Exception):
    pass


_known_kwargs = {"showall", "learn", "egtbmetric", "endgame"}
def _prepare_params(kwargs, board:chess.Board=None) -> dict | CDBStatus:
    for kw in kwargs:
        if kw not in _known_kwargs:
            raise CDBError(f"unknown api argument: {kw}")
    kwargs['json']  = 1
    if board:
        if board.is_game_over():
            return CDBStatus.GameOver
        kwargs['board'] = board.fen()
    return kwargs


def _parse_status(text, board:chess.Board=None, raisers=None) -> CDBStatus:
    if raisers is None:
        raisers = set(CDBStatus) - {CDBStatus.Success, CDBStatus.UnknownBoard}
    try:
        status = CDBStatus(text)
    except ValueError as e: # TODO: can we replace the error that the enum produces in the first place?
        raise CDBError(f"problem with query (board: {board.fen() if board else None})") from e
    if status in raisers:
        raise CDBError(f"{status=} (board: {board.fen() if board else None})")
    return status


# some notes:
# 'queue', request for analysis, does a refresh of all child nodes, with recursive deep refresh of pv-lines thereof, minimum depth 20(ish) ply max 100 ply
# whereas 'query' does only a shallow child refresh, a ply or two.
# (exception: when too little material on the board, ....???)
# additionally, for classical only, a background process tries its best to ensure all positions are connected to the
# startpos in some way, every few days or so
# 'store' effectively creates a new child node, however directly 'queue'ing the child node position will automatically link that child to its parent.

# query retval is json with keys "moves", "ply", "status", moves is list, each move has "note", "rank", "san", "score", "uci", "winrate"
# moves: "rank" is similar to the notation in "notes", 2=best, 1=good, 0=worse, but may show 0 for all moves in a bad pos
#        "notes" is as on the web interface, counting child nodes and annotating the move
# ply: the shortest path from the rootpos to the classical startpos

# current testing indicates max rate of ~400-500 req/s, with no added rate above concurrency=256
# currently unknown what is the bottleneck. maybe chess.Board.fen?

class AsyncCDBClient(httpx.AsyncClient):
    '''Asynchronous Python interface to the CDB API, using `httpx` and `chess`.
    
    All queries require a chess.Board arugment, and optionally accept a subset
    of the following standard options: `showall`, `learn`, `egtbmetric`, `endgame`
    all 1 or 0 except egtbmetric, which is "dtm" or "dtz"
        showall = include unknown moves
        learn = enable autoqueueing
        endgame = show only TB data
    
    `raisers` is an optional set of statuses to raise on, defaulting to anything other than Success.

    `self.concurrency` may be tweaked as desired for mass requests to CDB, defaulting to 128.
    '''

    # TODO: http2?
    def __init__(self, **_kwargs):
        '''
        This httpx.AsyncClient subclass may be initialized with any kwargs of the parent.
        Also, `self.concurrency` may be set here.
        '''
        if 'concurrency' in _kwargs:
            self.concurrency = _kwargs['concurrency']
            del _kwargs['concurrency']
        else:
            self.concurrency = 128

        kwargs = {
                  #'base_url': _CDBURL,
                  'headers': {'user-agent': 'noobchessdbpy'},
                  'timeout': 30,
                  'limits': httpx.Limits(max_keepalive_connections=None,
                                         max_connections=None,
                                         keepalive_expiry=30
                                        ),
                  #'http2': True,
                  **_kwargs
                 }
        super().__init__(**kwargs)

    ####################################################################################################################

    async def query_all(self, board:chess.Board, raisers:set=None, **kwargs) -> dict | CDBStatus:
        '''Query all known moves for a given position

        Query retval is json with keys "moves", "ply", "status"
        "moves" is a list, sorted by score, each move has "note", "rank", "san", "score", "uci", "winrate"
            "score" is in centipawns, from side-to-move perspective
            "winrate" is ? (expected score or 1-drawrate?)
            "rank" is like the notation in "Notes", 2=best, 1=good, 0=worse but may show 0 for all moves in a bad pos
            "notes" is as on the web interface, counting child nodes and annotating the move
            "san" and "uci" describe the move itself in the respective notation
        "ply": the shortest path from the rootpos to the classical startpos
        "status": see CDBStatus

        returns a CDBStatus if the json status isn't CDBStatus.Success or CDBStatus.UnknownBoard
        '''
        params = _prepare_params(kwargs, board)
        if not isinstance(params, dict):
            return params
        params['action'] = 'queryall'

        resp = await self.get(url=_CDBURL, params=params)

        json = resp.json()
        #pprint(json)
        #print(resp.http_version)
        #print(json['status'])
        if (err := _parse_status(json['status'], board)) is not CDBStatus.Success:
            return err
        return json


    async def queue(self, board:chess.Board, raisers:set=None, **kwargs) -> CDBStatus:
        '''Queue for later analysis a single position'''
        params = _prepare_params(kwargs, board)
        if not isinstance(params, dict):
            return params
        params['action'] = 'queue'

        resp = await self.get(url=_CDBURL, params=params)

        json = resp.json()
        #print(json)
        return _parse_status(json['status'], board, raisers) if json else json # queue in TB => empty resp (violates type)

    async def _clear_limit(self, **kwargs) -> CDBStatus:
        params = _prepare_params(kwargs)
        if not isinstance(params, dict):
            return params
        params['action'] = 'clearlimit'

        resp = await self.get(url=_CDBURL, params=params)

        json = resp.json()
        return _parse_status(json['status'])


    ####################################################################################################################

    async def mass_request(self, api_call, producer_task, *producer_args, collect_results=False):
        '''
        Generic mass requester. Takes API call, producer task, producer args, and whether to collect results.
        The producer task MUST accept, and close when complete, its `send_taskqueue` trio.MemorySendChannel. Other args
        come after `send_taskqueue`.

        Constructs the consumer task to make the API call, and constructs the queue from producer to consumers.

        If collecting results, they're tuples of `(producer_arg, api_call(producer_arg))`.
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



        
