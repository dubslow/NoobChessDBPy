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

_board_with_underscores = lambda fen: chess.Board(fen.replace('_', ' '))
_board_with_underscores.__name__ = "chess.Board" # for argparse help messages

class CDBArgs(Enum):
    '''
    A list of common arguments amongst the many scripts (can be used to automatically include them)
    '''
    Concurrency     = ('-c', '--concurrency'), {'type': int, 'default': AsyncCDBClient.DefaultConcurrency,
                      'help': "maximum number of simultaneous requests (default: %(default)s [polite rather than optimal])"}
    User            = ('-u', '--user'), {'default': '',
                      'help': 'add this username to the HTTP User-Agent header (recommended)'}
    AutoClear       = ('-a', '--autoclear'), {'action': 'store_true', 'help': argparse.SUPPRESS}
                      # "hidden" argument for "advanced" users

    Fen             = ('-f', '--fen'), {'type': _board_with_underscores, 'default': chess.Board(),
                      'help': "the FEN of the root position (default: classical startpos)"}
    LimitCount      = ('-l', '--count', '--limit-count'), {'type': int, 'default': math.inf,
                      'help': 'the maximum number of positions to request'}
    PlyMax          = ('-p', '--ply', '--limit-ply'), {'type': int, 'default': math.inf,
                      'help': 'the maximum allowed ply relative the root'}
    OutputFilename  = ('-o', '--output'), {'default': argv[0].replace('.py', '.txt'),
                      'help': "filename to write request results to (default: %(default)s)"}

    NearPVMargin    = ('-m', '--margin'), {'type': int, 'default': 5, 'choices': range(0, 200), 'metavar': "cp_margin",
                      'help': '''centipawn margin for what's considered "near PV"'''
                                ' (choose from [0,200)) (default: %(default)s)'}
    NearPVDecay     = ('-d', '--decay', '--margin-decay'), {'type': float, 'default': 1.0,
                      'help': 'linear rate per ply by which to shrink the margin (default: %(default)s)'}
    NearPVBranchMax = ('-b', '--branching', '--max-branch'), {'type': int, 'default': math.inf,
                      'help': 'maximum branch factor at any given node (default: %(default)s)'}

    def add_to_parser(self, parser, **_kwargs):
        '''
        Add argument `self` to the given parser, optionally overwriting kwargs.
        '''
        args, kwargs = self.value
        kwargs.update(_kwargs) #kwargs |= _kwargs
        parser.add_argument(*args, **kwargs)

    @staticmethod
    def add_args_to_parser(parser, *args):
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
        CDBArgs.add_args_to_parser(parser, CDBArgs.Concurrency, CDBArgs.User, CDBArgs.AutoClear)

    @staticmethod
    def add_api_flat_args_to_parser(parser):
        '''
        Like `add_api_args_to_parser` except excluding Concurrency, for use in scripts which spawn based on inputs.
        '''
        CDBArgs.add_args_to_parser(parser, CDBArgs.User, CDBArgs.AutoClear)
