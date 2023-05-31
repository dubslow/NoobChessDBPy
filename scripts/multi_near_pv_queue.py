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
loop `near_pv_queue_any.py` over several input positions. WIP
'''

import argparse
from itertools import cycle
import logging
import math
import shlex
from sys import argv
import time

import trio
import chess.pgn

from noobchessdbpy.api import CDBStatus
from noobchessdbpy.library import AsyncCDBLibrary, CDBArgs
import near_pv_queue_any

logging.basicConfig(
    format="%(levelname)s [%(asctime)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO
)

########################################################################################################################

def read_input(args):
    sub_argss = []
    with open(args.inputfile) as handle:
        for line in handle:
            if not line:
                continue
            line = shlex.split(line, comments=True)
            if line:
                sub_argss.append(near_pv_queue_any.parser.parse_args(line))
    return sub_argss

async def qpv(args, board):
    async with AsyncCDBLibrary(args=args) as lib:
        await lib.query_pv(board)

def loop(args, sub_argss):
    # querypv L2, queue L1, querypv L3, queue L2, querypv L4, queue L3
    sub_argss_qpv = sub_argss[1:] + sub_argss[:1] # rotated right by 1
    for qpv_args, queue_args in zip(cycle(sub_argss_qpv), cycle(sub_argss)):
        print("running querypv on", repr(qpv_args.fen))
        trio.run(qpv, args, qpv_args.fen)
        print("sleeping 2s for DB's sake")
        time.sleep(2)
        print("running near_pv_queue_any on", repr(queue_args.fen))
        near_pv_queue_any.main(queue_args)
        print("")

def main(args):
    sub_argss = read_input(args)
    loop(args, sub_argss)

########################################################################################################################

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('inputfile', help='the text file whose lines are args to each near_pv_queue_any.py instance')
CDBArgs.add_api_flat_args_to_parser(parser)

if __name__ == '__main__':
    args = parser.parse_args()
    main(args)
