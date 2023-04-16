#! python3.11

import httpx
import chess
from enum import StrEnum, auto
from pprint import pprint

_CDBURL = 'http://www.chessdb.cn/cdb.php'

class CDBStatus(StrEnum):
    '''Enum used for non-moves return values from CDB.
    
    Success = request for analysis accepted
    
    GameOver includes checkmate,
    stalemate, threefold, 50 move, etc
    
    UnknownBoard = position not in DB (but maybe now added)
    
    NoBestMove = position exists, but nevertheless no moves
    
    TrivialBoard = request for analysis was ignored because trivial position
    '''
    Success      = auto()
    GameOver     = auto()
    UnknownBoard = auto()
    NoBestMove   = auto()
    TrivialBoard = auto()


#def _collect_params(params, **kwargs):
#    return {k: v for k, v in kwargs.items() if v is not None}


def _parse_errors(text, board:chess.Board) -> CDBStatus | None:
    match text:
        case str() as t if 'nvalid' in t: # Fugly
            raise ValueError(f'invalid board: {board.fen()}')
        case "unknown":
            return CDBStatus.UnknownBoard
        case "nobestmove":
            return CDBStatus.NoBestMove
        case "":
            return CDBStatus.TrivialBoard
    return None


class AsyncCDBClient(httpx.AsyncClient):
    '''Asynchronous Python interface to the CDB API, using `httpx` and `chess`.
    
    All queries require a chess.Board arugment, and optionally accept a subset of
    the following standard options:
    
    showall, learn, egtbmetric, endgame
    
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


    async def query_all_known_moves(self, board:chess.Board, showall=None, egtbmetric=None, learn=None) -> []:
        if board.is_game_over(claim_draw=True):
            return CDBStatus.GameOver

        params = {'action': 'queryall',
                  'board': board.fen(),
                  'json': 1
                 }
        #if showall is not None:
        #    params['showall'] = showall
        #if egtbmetric is not None:
        #    params['egtbmetric'] = egtbmetric
        #if learn is not None:
        #    params['learn'] = learn

        resp = await self.get(url=_CDBURL, params=params)
        json = resp.json()
        pprint(json)
        if (err := _parse_errors(json['status'], board)) is not None:
            return err
        return json
       
            
