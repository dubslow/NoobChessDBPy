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
    as a subclass of the client. However each method requires a nursery to be passed so that it may
    spawn its work in parallel.'''
    # Maybe we can later export static variations which construct a new client on each call?
    def __init__(self, **kwargs):
        '''This AsyncCDBClient subclass may be initialized with any kwargs of the parent class'''
        super().__init__(**kwargs)


    def analyze_single_line(self, pgn:str, nursery:trio.Nursery):
        '''Given a single line of moves, `queue` for analysis all positions in this line.'''
        game = chess.pgn.read_game(StringIO(pgn))
        # chess.pgn handles variations, and silently we don't actually verify if this pgn has no variations.
        for node in game.mainline():
            nursery.start_soon(self.request_analysis, node.board())
