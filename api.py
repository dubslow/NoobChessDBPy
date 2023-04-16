#! python3.11

'''The python wrapper to the CDB API. In general, create an AsyncCDBClient instance, and use its methods to make API calls.
This class inherits from httpx.AsyncClient, and forwards kwargs.
API call return values are generally json or a CDBStatus value.'''

import httpx
import chess
from enum import StrEnum, auto
from pprint import pprint

_CDBURL = 'http://www.chessdb.cn/cdb.php'

class CDBStatus(StrEnum):
    '''Enum used for non-moves return values from CDB.
    
    Ok = query served
    Success = request for analysis accepted
    GameOver includes checkmate, stalemate, threefold, 50 move, etc
    UnknownBoard = position not in DB (but maybe now added)
    NoBestMove = position exists, but nevertheless no moves
    TrivialBoard = request for analysis was ignored because trivial position
    LimitExceeded = too many requests from this client/ip/whatever
    '''
    Success       = "ok"
    GameOver      = auto()
    InvalidBoard  = "invalid board"
    UnknownBoard  = "unknown"
    NoBestMove    = "nobestmove"
    TrivialBoard  = ""
    LimitExceeded = "rate limit exceeded"

class CDBError(Exception):
    pass

#def _collect_params(params, **kwargs):
#    return {k: v for k, v in kwargs.items() if v is not None}


def _prepare_params(board:chess.Board) -> dict | CDBStatus:
    if board.is_game_over(claim_draw=True):
        return CDBStatus.GameOver
    return {'board': board.fen(),
            'json': 1
           }


def _parse_status(text, board:chess.Board, raisers=None) -> CDBStatus:
    if raisers is None:
        raisers = set(CDBStatus) - {CDBStatus.Success}
    try:
        status = CDBStatus(text)
    except ValueError as e: # TODO: can we replace the error that the enum produces in the first place?
        raise CDBError(f"problem with query ({board.fen()=})") from e
    if status in raisers:
        raise CDBError(f'{status}: {board.fen()=}')
    return status


# some notes:
# 'queue', request for analysis, does a refresh of all child nodes, with recursive deep refresh of pv-lines thereof, minimum depth 20(ish) ply max 100 ply
# whereas 'query' does only a shallow child refresh, a ply or two.
# (exception: when too little material on the board, ....???)
# additionally, for classical only, a background process tries its best to ensure all positions are connected to the
# startpos in some way, every few days or so
# 'store' effectively creates a new child node, however directly 'queue'ing the child node position will automatically link that child to its parent.

# moves retval: "rank" is similar to the notation in "notes", 2=best, 1=good, 0=worse, but may show 0 for all moves in a bad pos
#               "notes" is as on the web interface, counting child nodes and annotating the move
# ply retval: the shortest path from the rootpos to the classical startpos

class AsyncCDBClient(httpx.AsyncClient):
    '''Asynchronous Python interface to the CDB API, using `httpx` and `chess`.
    
    All queries require a chess.Board arugment,
    
    # and optionally accept a subset of the following standard options:
    # `showall`, `learn`, `egtbmetric`, `endgame`

    `raisers` is an optional set of statuses to raise on, defaulting to anything other than Success.
    '''

    # TODO: http2?
    def __init__(self, **_kwargs):
        '''This httpx.AsyncClient subclass may be initialized with any kwargs of the parent.'''
        kwargs = {
                  #'base_url': _CDBURL,
                  'headers': {'user-agent': 'noobchessdbpy'},
                  'timeout': 30,
                  **_kwargs
                 }
        super().__init__(**kwargs)


    async def query_all_known_moves(self, board:chess.Board, showall=None, egtbmetric=None, learn=None) -> dict | CDBStatus:
        params = _prepare_params(board)
        params['action'] = 'queryall',
        #if showall is not None:
        #    params['showall'] = showall
        #if egtbmetric is not None:
        #    params['egtbmetric'] = egtbmetric
        #if learn is not None:
        #    params['learn'] = learn

        resp = await self.get(url=_CDBURL, params=params)
        json = resp.json()
        pprint(json)
        if (err := _parse_status(json['status'], board)) is not None:
            return err
        return json


    async def request_analysis(self, board:chess.Board, raisers:set=None) -> CDBStatus:
        params = _prepare_params(board)
        params['action'] = 'queue'

        resp = await self.get(url=_CDBURL, params=params)

        json = resp.json()
        pprint(json)
        return _parse_status(json['status'], board, raisers)
            


