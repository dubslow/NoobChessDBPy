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
A skeleton example: queries positions breadth first, returning the moves-results from CDB, and optionally writing to
file.
'''

import argparse
import logging
import math

import trio
import chess

from noobchessdbpy.api import AsyncCDBClient
from noobchessdbpy.library import AsyncCDBLibrary, BreadthFirstState

logging.basicConfig(
    format="%(levelname)s [%(asctime)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO
)

########################################################################################################################

async def query_bfs(rootpos:str=None, maxply=math.inf, count=math.inf, outfile=None, concurrency=AsyncCDBClient.DefaultConcurrency):
    if rootpos is None:
        rootpos = chess.Board()
    else:
        rootpos = chess.Board(rootpos)

    print(f"{maxply = }, {count = }, {concurrency = }")
    async with AsyncCDBLibrary(concurrency=concurrency, user='Dubslow') as lib:
        results = await lib.query_breadth_first(BreadthFirstState(rootpos), maxply=maxply, count=count)
    #results = {b.fen(): j for b, j in results}
    #for res in results:
    #    print(res['moves'][0:2])
    # the user may write whatever processing of interest here
    if outfile:
        # raw json probably isn't terribly legible on its own
        with open(outfile, 'a') as outhandle:
            outhandle.write('\n'.join(f"{b.fen()}\n{j}" for b, j in results) + '\n')
        


if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    limits = parser.add_argument_group('limits', 'breadth-first limits, at least one of these is required:')
    limits.add_argument('-l', '--count', '--limit-count', type=int, help='the maximum number of positions to query')
    limits.add_argument('-p', '--ply', '--limit-ply', type=int, help='the max ply from the root to query')
    limits.add_argument('-i', '--infinite', action='store_true', help='unlimited querying')

    parser.add_argument('-f', '--fen',
                help="the FEN of the rootpos from which to start breadth-first searching (default: classical startpos)")
    parser.add_argument('-c', '--concurrency', type=int, default=AsyncCDBClient.DefaultConcurrency,
                                                         help="maximum number of parallel requests")
    parser.add_argument('-o', '--output', help="filename to append query results to")

    args = parser.parse_args()
    if not args.count and not args.ply and not args.infinite:
        parser.error("at least one of the limits is required (see --help)")
    elif args.infinite and (args.count or args.ply):
        parser.error("cannot have limits and --infinite (see --help)")

    if args.count is None:
        args.count = math.inf
    if args.ply is None:
        args.ply = math.inf

    trio.run(query_bfs, args.fen, args.ply, args.count, args.output, args.concurrency)
