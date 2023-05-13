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
This script reads JSON files, one at a time: read FENs from json of {fen: int}, deduplicate the positions,
rinse and repeat, and cross-deduplicate between all files. Then mass-queue the cross-deduplicated positions into CDB.
(Note: queueing near-root positions can be quite expensive, so use this with caution. TODO: write a better form that
does only some queueing, and some querying instead)
Note: queue order is arbitrary.

(One can also queue PGN files, see queue_pgn.py)
'''

import argparse
import json
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

async def parse_and_queue_pgn(args):
    async with AsyncCDBLibrary(concurrency=args.concurrency) as lib:
        all_positions, n, u_sub = set(), 0, 0
        for i, filename in enumerate(args.filenames):
            with open(filename) as filehandle:
                jfens = json.loads(filehandle.read())
            x = len(jfens)
            this_positions = set(jfens.keys())
            this_len = len(this_positions)
            print(f"after deduplicating {filename}, found {this_len} unique positions from {x} total, {this_len/x:.2%} unique rate")
            n += x
            u_sub += this_len
            all_positions |= this_positions
            u = len(all_positions)
            if i > 0:
                print(f"after cross-deduplication, found {u} cross-unique positions from {u_sub} sub-unique from {n} "
                      f"total, {u/n if n else math.nan:.2%} unique rate")
        print(f"now mass queueing {u} positions")
        await lib.mass_queue_set(all_positions)
        print(f"all {u} positions have been queued for analysis")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('filenames', nargs='+',
                        help="""A list of filenames to read JSON FEN from. """)
    parser.add_argument('-c', '--concurrency', type=int, default=AsyncCDBClient.DefaultConcurrency,
                                                      help="maximum number of parallel requests (default: %(default)s)")

    args = parser.parse_args()
    trio.run(parse_and_queue_pgn, args)
