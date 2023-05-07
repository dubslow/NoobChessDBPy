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
The python wrapper to the CDB API. In general, create an AsyncCDBClient instance, and use its methods to make API calls.
This class inherits from httpx.AsyncClient, and forwards kwargs thereto.

API call return values are generally json (i.e. a python dict) or a CDBStatus value.

Also exposed here are `CDBStatus`, an enum reflecting the status of a single API response, and `CDBError`, which is a
generic `Exception` for when those statuses are bad.

See also the docstrings of these objects.
'''

__all__ = ['CDBStatus', 'CDBError', 'AsyncCDBClient']

import trio
import httpx
import chess

from enum import Enum, auto
from pprint import pprint

_CDBURL = 'https://www.chessdb.cn/cdb.php'

class CDBStatus(Enum):
    '''
    Enum used for non-moves return values from CDB.

    Success = normal request and response
    GameOver includes checkmate, stalemate
    InvalidBoard is what it sounds like
    UnknownBoard = position not in DB (but maybe now added as a result)
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


# Maybe these helper funcs should be static methods on the Client below?
_known_cdb_kwargs = {"showall", "learn", "egtbmetric", "endgame"}
def _prepare_params(kwargs, board:chess.Board=None) -> dict | CDBStatus:
    for kw in kwargs:
        if kw not in _known_cdb_kwargs:
            raise CDBError(f"unknown api argument: {kw}")
    kwargs['json']  = 1
    if board:
        if board.is_game_over():
            return CDBStatus.GameOver
        kwargs['board'] = board.fen()
    return kwargs

def _parse_status(text, board:chess.Board=None, raisers=None) -> CDBStatus:
    if raisers is None:
        raisers = set(CDBStatus) - {CDBStatus.Success, CDBStatus.UnknownBoard, CDBStatus.NoBestMove}
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

# current testing indicates max rate of ~400-500 req/s, with no added rate above concurrency=256, on my cpu at least
# currently unknown what is the bottleneck. maybe chess.Board.fen()?


class AsyncCDBClient(httpx.AsyncClient):
    '''
    Asynchronous Python interface to the CDB API, using `httpx` and `chess`.
    
    All queries require a chess.Board arugment, and optionally accept some subset
    of the following standard options: `showall`, `learn`, `egtbmetric`, `endgame`
    all 1 or 0 except egtbmetric, which is "dtm" or "dtz"
        showall = include unknown moves
        learn = enable autoqueueing
        endgame = show only TB data
    
    `raisers` is an optional set of statuses to raise on, defaulting to anything other than Success.

    `self.concurrency` may be tweaked as desired for mass requests to CDB, defaulting to DefaultConcurrency.
    `self.user` is the User-Agent attached to http requests, and can only be set via the constructor.
    '''
    DefaultConcurrency = 128
    _known_client_kwargs = {"concurrency": DefaultConcurrency, "user": ""}
    def _process_kwargs(self, kwargs):
        # Set our kwargs on self, then delete them, and the rest are forwarded to super()
        for key, defaultval in self._known_client_kwargs.items():
            if key in kwargs:
                setattr(self, key, kwargs[key])
                del kwargs[key]
            else:
                setattr(self, key, defaultval)

    # TODO: http2?
    def __init__(self, **kwargs):
        '''
        This httpx.AsyncClient subclass may be initialized with any kwargs of the parent.
        Also, `self.concurrency` and `self.user` can be set here.
        '''
        # take our kwargs, and delete them from the dict
        self._process_kwargs(kwargs)
        # kwargs is now only those meant for super(), and we set some defaults too before forwarding
        self_kwargs = {#'base_url': _CDBURL,
                       'headers':   {'user-agent': self.user + bool(self.user) * '/' + 'noobchessdbpy'},
                       'timeout':   30,
                       'limits':    httpx.Limits(max_keepalive_connections=None,
                                                 max_connections=None,
                                                 keepalive_expiry=30),
                       #'http2':    True,
                      }
        super().__init__(**self_kwargs, **kwargs)

    ####################################################################################################################

    async def query_all(self, board:chess.Board, raisers:set=None, **kwargs) -> dict | CDBStatus:
        '''
        Query all known moves for a given position

        Query retval is json with keys "moves", "ply", "status"
        "moves" is a list, sorted by score, each move has "note", "rank", "san", "score", "uci", "winrate"
            "score" is in centipawns, from side-to-move perspective
            "winrate" is ? (expected score or 1-drawrate?)
            "rank" is like the notation in "Notes", 2=best, 1=good, 0=worse but may show 0 for all moves in a bad pos
            "notes" is as on the web interface, counting child nodes and annotating the move
            "san" and "uci" describe the move itself in the respective notation
        "ply": the shortest path from the rootpos to the classical startpos
        "status": see CDBStatus

        returns a CDBStatus if the json status isn't CDBStatus.Success
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

        If collecting results, they're tuples of `(producer_arg, api_call(producer_arg))`. The caller can easily convert
        this to a dict if the arg is hashable.
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



        
