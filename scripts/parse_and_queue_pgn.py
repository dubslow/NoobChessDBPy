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
This script reads a PGN file, reads games from that file into memory, finds all positions in the games (including PVs
stored in comments), deduplicates the positions, and mass-queues the resulting unique positions. Although this accepts
a list of filenames, each file is processed and deduplicated individually. (Note: queueing near-root positions can be
quite expensive, so use this with caution. TODO: write a better form that does some queueing, some querying only)
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

async def parse_and_queue_pgn(args):
    async with AsyncCDBLibrary(concurrency=args.concurrency) as lib:
        for filename in args.filenames:
            with open(filename) as filehandle:
                all_positions = lib.parse_pgn(filehandle, args.start, args.count)
            n = len(all_positions)
            print(f"now mass queueing {n} positions")
            await lib.mass_queue(all_positions)
            print(f"all {n} positions have been queued for analysis")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('filenames', nargs='+',
                        help="""A list of filenames to read PGN from. Each is processed and deduplicated individually;
                             to deduplicate everything, cat them all into one file.""")
    parser.add_argument('-l', '--count', '--limit-count', type=int, default=math.inf,
                        help='the maximum number of games to process from each file')
    parser.add_argument('-s', '--start', type=int, default=0,
                        help='the number of games to skip from the beginning of each file')
    parser.add_argument('-c', '--concurrency', type=int, default=AsyncCDBClient.DefaultConcurrency,
                                                         help="maximum number of parallel requests (default: %(default)s)")

    args = parser.parse_args()
    trio.run(parse_and_queue_pgn, args)
