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
An implementation detail: coalesce common arguments amongst all the scripts here.
'''

########################################################################################################################

import argparse
from enum import Enum
import math
from sys import argv
from typing import Sequence

import chess

from ..api import AsyncCDBClient

__all__ = ['CDBArgs']

########################################################################################################################

class CDBArgs(Enum):
    '''
    A list of common arguments amongst the many scripts (can be used to automatically include them)
    '''
    Concurrency    = ('-c', '--concurrency'), {'type': int, 'default': AsyncCDBClient.DefaultConcurrency,
                     'help': "maximum number of simultaneous requests (default: %(default)s, which is lower than optimal)"}
    User           = ('-u', '--user'), {'default': '',
                     'help': 'add this username to the HTTP User-Agent header (recommended)'}
    Fen            = ('-f', '--fen'), {'type': lambda fen: chess.Board(fen.replace('_', ' ')), 'default': chess.Board(),
                     'help': "the FEN of the root position (default: classical startpos)"}
    LimitCount     = ('-l', '--count', '--limit-count'), {'type': int, 'default': math.inf,
                     'help': 'the maximum number of positions to request'}
    PlyMax         = ('-p', '--ply', '--limit-ply'), {'type': int, 'default': math.inf,
                     'help': 'the maximum allowed ply relative the root'}
    OutputFilename = ('-o', '--output'), {'default': argv[0].replace('.py', '.txt'),
                     'help': "filename to write request results to (default: %(default)s)"}
    #AutoClear      = ('-a', '--autoclear'), {'action': 'store_true'} TODO: implement this in API
                     # no help message, "hidden" argument for "advanced" users

    def add_to_parser(self, parser, **_kwargs):
        '''
        Add argument `self` to the given parser, optionally overwriting kwargs.
        '''
        args, kwargs = self.value
        kwargs |= _kwargs
        parser.add_argument(*args, **kwargs)

    @staticmethod
    def add_args_to_parser(parser, args:Sequence): # Sequence[CDBArgs]
        '''
        Given a sequence of members of this class, add each of them to the `parser`. (This is just a simple loop.)
        '''
        for arg in args:
            arg.add_to_parser(parser)

    @staticmethod
    def add_api_args_to_parser(parser): # are these static reference to CDBArgs a problem?
        '''
        Add the standard API arguments (`AsyncCDBClient._known_client_kwargs`) to the parser.
        '''
        CDBArgs.add_args_to_parser(parser, (CDBArgs.Concurrency, CDBArgs.User)) # CDBArgs.AutoClear

    @staticmethod
    def add_api_flat_args_to_parser(parser):
        '''
        Like `add_api_args_to_parser` except excluding Concurrency, for use in scripts which spawn based on inputs.
        '''
        CDBArgs.add_args_to_parser(parser, (CDBArgs.User, )) # CDBArgs.AutoClear
