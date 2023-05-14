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
lol
'''

import argparse
import logging
import math

import trio
import chess.pgn

from noobchessdbpy.api import AsyncCDBClient
from noobchessdbpy.library import AsyncCDBLibrary

logging.basicConfig(
    format="%(levelname)s [%(asctime)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO
)

async def cdb_iterate(args):
    async with AsyncCDBLibrary(concurrency=args.concurrency) as lib:
        results = await lib.cdb_iterate(args.fen, lib.cdb_explore_visitor, args.margin)
    # user can write any post-processing they like here
    if args.output:
        with open(args.output, 'w') as f:
            f.write('{\n' + '\n'.join(f'''"{key}": {val}''' for key, val in results.items()) + '\n}\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument('-f', '--fen', type=chess.Board, default=chess.Board(),
          help="the FEN of the root position from which to start breadth-first searching (default: classical startpos)")
    parser.add_argument('-m', '--margin', type=int, default=5, choices=range(0, 200),
                        help="centipawn margin for what's considered near PV")
    parser.add_argument('-c', '--concurrency', type=int, default=AsyncCDBClient.DefaultConcurrency,
                                                      help="maximum number of parallel requests (default: %(default)s)")
    from sys import argv
    parser.add_argument('-o', '--output', default=argv[0].replace('.py', '.txt'),
                        help="filename to write query results to (defaults to scriptname.txt)")

    args = parser.parse_args()
    trio.run(cdb_iterate, args)
