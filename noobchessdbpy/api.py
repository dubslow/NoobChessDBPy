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
This class inherits from `httpx.AsyncClient`, and forwards kwargs thereto.

API call return values are generally json (i.e. a python dict) or a CDBStatus value.

Also exposed here are `CDBStatus`, an enum reflecting the status of a single API response, and `CDBError`, which is a
generic `Exception` for when those statuses are bad.

See also the docstrings of these objects.

This module is *nearly* eventloop agnostic, consisting only of async functions and methods plus a brief reference to
`trio.sleep` for implementing retries. In principle it's nearly trivial to use a different eventloop with this module.
'''

__all__ = ['CDBStatus', 'CDBError', 'AsyncCDBClient']

########################################################################################################################

from enum import Enum, auto

import chess
import httpx
import trio

########################################################################################################################

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
    TrivialBoard  = None # type consistency is too much to ask for I guess
    LimitExceeded = "rate limit exceeded"
    LimitCleared  = "rate limit cleared"

class CDBError(Exception):
    pass

########################################################################################################################
# some notes:
# 'queue', request for analysis, does a refresh of all child nodes, with recursive deep refresh of pv-lines thereof,
# minimum depth 20(ish) ply max 100 ply
# whereas 'query' does only a shallow child refresh, a ply or two.
# (exception: when too little material on the board, ....???)
# additionally, for classical only, a background process tries its best to ensure all positions are connected to the
# startpos in some way, every few days or so
# 'store' effectively creates a new child node, however directly 'queue'ing the child node position will automatically
# link that child to its parent.

# query retval is json with keys "moves", "ply", "status", moves is list, each move has "note", "rank", "san", "score", "uci", "winrate"
# moves: "rank" is similar to the notation in "notes", 2=best, 1=good, 0=worse, but may show 0 for all moves in a bad pos
#        "notes" is as on the web interface, counting child nodes and annotating the move
# ply: the shortest path from the rootpos to the classical startpos

# current testing indicates max rate of ~400-500 req/s, with no added rate above concurrency=256, on my cpu at least
# currently unknown what is the bottleneck. maybe chess.Board.fen()?


class AsyncCDBClient(httpx.AsyncClient):
    '''
    Asynchronous Python interface to the CDB API, using `httpx` and `chess`.
    
    All API calls require a chess.Board arugment, and optionally accept some subset
    of the following standard options: `showall`, `learn`, `egtbmetric`, `endgame`
    all 1 or 0 except egtbmetric, which is "dtm" or "dtz"
        showall = include unknown moves
        learn = enable autoqueueing
        endgame = show only TB data
    
    `raisers` is an optional set of statuses to raise on, defaulting to {InvalidBoard, LimitExceeded} (pass an empty set
    to disable).

    All API call retvals have some sort of `CDBStatus`. For the `query` family, they return a dictionary reflecting CDB's
    json responses, and the key `"status"` is the only guaranteed field, whose value is the `CDBStatus`. For the `queue`
    family, the `CDBStatus` is directly returned instead of a json dict.

    By default, if the status is `InvalidBoard`, then a CDBError is raised, tho that behavior can be overridden (or
    caught with `try` of course). `GameOver` means the request wasn't even sent over the wire (but was rather
    shortcircuited by `chess.Board.is_game_over`).

    For the `query` family, any value other than `Success` means the rest of the dict is invalid, so checking the status
    is required before diving into the CDB results.


    `self.concurrency` may be tweaked as desired for mass requests to CDB, defaulting to DefaultConcurrency.
    `self.user` is the User-Agent attached to http requests, and can only be set via the constructor.

    The default concurrency is less than "optimal" for maximizing requests/second. On my system, roughly 192 is optimal,
    while 128 and 256 are near-optimal -- giving a max rate on the order of 400-500 reqs/s. However, just one person
    running at ~max rate can overwhelm the backend, nevermind two. Therefore, the default is considerably lower to
    encourage user politeness (to CDB itself and to other users who also suffer when the backend is overloaded).
    '''
    DefaultConcurrency = 32
    _known_client_kwargs = {"concurrency": DefaultConcurrency, "user": "", 'autoclear': False}
    # The `autoclear` kwarg is undocumented, only meant to aid users in the know. It automatically clears the daily
    # per-IP query limit when triggered.
    #
    # In addition to regular kwargs, we also accept the special kw "args": its value is a namespace from which we read
    # the other kwargs (but any actual kwargs override the "args" values). In "args", we ignore unknown kwargs, while
    # regular unknown kwargs are forwarded to the parent class.
    # "args" is useful to simplify passing command line args to this constructor via CDBArgs.
    def _process_kwargs(self, kwargs):
        # Set our kwargs on self, then delete them, and the rest are forwarded to super()
        # But also special handling for `args`, per the above comment
        # This definitely isn't my favorite code I've ever written... quite inelegant (but it gets the job done I suppose)
        args = kwargs.get('args', ())
        for key, defaultval in self._known_client_kwargs.items():
            if key in kwargs:
                setattr(self, key, kwargs[key])
                del kwargs[key]
            elif key in args:
                setattr(self, key, getattr(args, key, defaultval))
            else:
                setattr(self, key, defaultval)
        if 'args' in kwargs:
            del kwargs['args']

    # TODO: http2?
    def __init__(self, **kwargs):
        '''
        This `httpx.AsyncClient` subclass may be initialized with any kwargs of the parent class.

        This class itself recognizes the `concurrency`, `user`, and `args` kwargs.
        - Any unrecognized kwargs are forwared to the parent class.
        - The "args" kw is a special convenience: it may contain a namespace from which the other recognized kwargs will
              be read. Unrecognized kwargs in "args" are *not* forwarded to the parent class.

        The default concurrency is "polite" rather than "optimal" to help prevent slamming CDB by default. Wise users
        may increase the concurrency beyond the default.
        '''
        # take our kwargs, and delete them from the dict
        self._process_kwargs(kwargs)
        # kwargs is now only those meant for super(), and we set some defaults too before forwarding
        super_kwargs = {#'base_url': _CDBURL,
                        'headers':  {'user-agent': self.user + bool(self.user) * '/' + 'noobchessdbpy'},
                        'timeout':  30,
                        'limits':   httpx.Limits(max_keepalive_connections=None,
                                                 max_connections=None,
                                                 keepalive_expiry=30),
                        #'http2':    True,
                      }
        super().__init__(**super_kwargs, **kwargs)

    #
    ####################################################################################################################
    ####################################################################################################################
    # First the under-the-hood internals common to each, every, any request made thru this API.

    _known_cdb_params = {"action", "move", "showall", "learn", "egtbmetric", "endgame"}
    @staticmethod
    def _prepare_params(kwargs, board:chess.Board=None):
        '''
        Prepare the parameters to the GET request (or return CDBStatus.GameOver or raise a CDBError)
        '''
        for kw in kwargs:
            if kw not in _known_cdb_params:
                raise CDBError(f"unknown api argument: {kw} (should be from {_known_cdb_args})")
        kwargs['json'] = 1
        if board:
            if board.is_game_over():
                return CDBStatus.GameOver
            kwargs['board'] = board.fen()
        return kwargs

    def _parse_status(self, json, board:chess.Board=None, raisers:set=None) -> None:
        '''Convert `json['status']` to a `CDBStatus` inplace'''
        if raisers is None:
            raisers = {CDBStatus.InvalidBoard, CDBStatus.LimitExceeded}
        if self.autoclear: # overwrite `raisers` input in this case
            raisers -= {CDBStatus.LimitExceeded}

        try:
            status = CDBStatus(json.get('status'))
        except ValueError as e: # TODO: can we replace the error that the enum produces in the first place?
            raise CDBError(f"problem with request: status {json.get('status')} "
                           f"(board: {board.fen() if board else None})")         from None
        json['status'] = status # convert before raising
        if status in raisers:
            raise CDBError(f"{status=} (board: {board.fen() if board else None})")

    async def _cdb_request(self, board:chess.Board, *, raisers:set=None, action, **kwargs) -> dict:
        '''
        Gather args into GET params, shortcirucit GameOver, retry HTTP errors, parse CDBStatus, return json
        '''
        params = self._prepare_params(kwargs, board)
        if params is CDBStatus.GameOver:
            return {'status': CDBStatus.GameOver}
        params['action'] = action
        #print(params)

        num_retries = 1000 # lol
        for i in reversed(range(num_retries)):
            try:
                resp = await self.get(url=_CDBURL, params=params)
                resp.raise_for_status()
            except httpx.HTTPError as err:
                if i == 0:
                    raise err
                else:
                    # possible extra newline to break \r stuff
                    print(('\n' if i == num_retries-1 else '') + f"caught HTTP error on {action} for {board=}:"
                          f" {err!r} retrying, have {i} retries left, waiting 20s...")
                    await trio.sleep(20)
            else: # HTTP success
                json = resp.json()
                self._parse_status(json, board, raisers)
                if json['status'] is CDBStatus.LimitExceeded and self.autoclear and action != 'clearlimit':
                    cs = await self._clear_limit() # recursion, but hopefully guarded here ^^ against infinite recursion
                    if cs is not CDBStatus.LimitCleared:
                        raise CDBError(f'clearing limit failed????!?!??!??!?? resp={c}')
                    #continue
                else:
                    #print(resp, resp.json())
                    return json

    #
    ####################################################################################################################
    ####################################################################################################################
    # Next, we provide and expose one function for each "action" as described by noob's docs:
    # https://www.chessdb.cn/cloudbookc_api_en.html
    # These are split into "query-like" and "queue-like", or more abstractly read ops and write ops.

    # In principle, we could or should be using some `functools.partial*` type thing for these, but those don't do any
    # sort of metadata and here we need the metadata, not only the docstring but also stuff like __name__ and
    # __qualname__ and others, so... here we are, repeating the signature twice for each copy in order to get all the
    # correct metadata. Maybe in the future we can have a sort of pattern like this....?
    #
    # @functools.partial_inplace(generic_func, arg='specialized1')
    # def specialized1_func(generic_func_signature):
    #     '''specialized docstring'''
    #     pass
    #
    # This still requires repeating the signature once, but that's less than below, and also it would be nice if
    # all the `partial*` flavors could optimize out the extra stack frame (but maybe that doesn't matter after 3.11)?
    # ...I should probably get my head out of the clouds lol

    async def query_all(self, board:chess.Board, raisers:set=None, **kwargs) -> dict:
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
        "status": see `CDBStatus`

        returns a `CDBStatus` if the json status isn't success
        '''
        return await self._cdb_request(board, raisers=raisers, **kwargs, action='queryall')

    async def query_best(self, board:chess.Board, raisers:set=None, **kwargs) -> dict:
        '''
        Get a "rank" == 2 move for this position. If in doubt, just use `query_all`. See also the CDB api doc page.
        (If there's a tie for best, a ~random one will be chosen.)

        json looks like: `{'status': 'ok', 'move': 'd2d4'}` (or `'egtb': 'd2d4'`)

        returns a `CDBStatus` if the json status isn't success
        '''
        return await self._cdb_request(board, raisers=raisers, **kwargs, action='querybest')

    async def query(self, board:chess.Board, raisers:set=None, **kwargs) -> dict:
        '''
        Get a "rank" > 0 move for this position. If in doubt, just use `query_all`. See also the CDB api doc page.

        json looks like: `{'status': 'ok', 'move': 'd2d4'}` (or `'egtb': 'd2d4'`)

        returns a `CDBStatus` if the json status isn't success
        '''
        return await self._cdb_request(board, raisers=raisers, **kwargs, action='query')

    async def query_search(self, board:chess.Board, raisers:set=None, **kwargs) -> dict:
        '''
        Get all "rank" > 0 moves for this position. If in doubt, just use `query_all`. See also the CDB api doc page.

        json looks like: `{'status': 'ok', 'search_moves': [{'uci': 'f2f4', 'san': 'f4'}, ...]}` (or `'egtb': 'd2d4'`)

        returns a `CDBStatus` if the json status isn't success
        '''
        return await self._cdb_request(board, raisers=raisers, **kwargs, action='querysearch')

    async def query_score(self, board:chess.Board, raisers:set=None, **kwargs) -> dict:
        '''
        Get just the score for this position (which is the bestmove's score). If in doubt, just use `query_all`.
        See also the CDB api doc page.

        json looks like: `{'status': 'ok', 'eval': 109, 'ply': 1}` (guess what position that was Kappa)

        returns a `CDBStatus` if the json status isn't success
        '''
        return await self._cdb_request(board, raisers=raisers, **kwargs, action='queryscore')

    async def query_pv(self, board:chess.Board, raisers:set=None, **kwargs) -> dict:
        '''
        Get CDB's current principal variation (best guess of perfect play) for this position.
        See also the CDB api doc page.

        json looks like: `{'status': 'ok', 'score': 109, 'depth': 41, 'pv': ['d7d5', 'h2h3', ...]}`
        (seriously it should be immediately obvious what position this is lol)

        returns a `CDBStatus` if the json status isn't success
        '''
        return await self._cdb_request(board, raisers=raisers, **kwargs, action='querypv')

    ####################################################################################################################

    async def _base_no_retval(self, board:chess.Board=None, *, action, raisers:set=None, **kwargs) -> CDBStatus:
        '''
        Private base method for no-retval-type actions. `queue` is probably the one you want

        returns a CDBStatus (or possibly raise a CDBError)
        '''
        json = await self._cdb_request(board, action=action, **kwargs)
        return json['status']

    async def queue(self, board:chess.Board, raisers:set=None, **kwargs) -> CDBStatus:
        '''
        Queue for later analysis a single position.
        '''
        return await self._base_no_retval(board, raisers=raisers, **kwargs, action='queue')

    async def store(self, board:chess.Board, move:chess.Move, raisers:set=None, **kwargs) -> CDBStatus:
        '''
        Like `queue` but only scores this move instead of sieving for 5 on the child.
        (This is how CDB elves report their results)
        '''
        return await self._base_no_retval(board, raisers=raisers, **kwargs, action='store', move=f"move:{move.uci()}")

    async def _clear_limit(self, **kwargs) -> CDBStatus:
        '''
        Use this to reset your IP addr's daily request limit.
        '''
        return await self._base_no_retval(**kwargs, action='clearlimit')

# end class AsyncCDBClient
########################################################################################################################

def strip_fen(fen:str):
    '''
    CDB ignores the last two FEN fields, and this will strip them. In uncommon cases, two positions may be identical
    except for the history, and using this enables deduplicating those for CDB purposes. That said, for e.g. PGN parsing,
    the difference can be on the order of several percent, a noticeable savings when at large magnitudes.
    '''
    parts = fen.split()
    size = len(parts)
    if size > 6:
        raise ValueError(f"found fen with more than 6 fields: {fen}")
    size = min(size, 4)
    return ' '.join(parts[:size])
        
