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
A skeleton example script: query positions in breadth first order, optionally writing the results to file.

One of the limit arguments is required, see below.
'''

import argparse
import logging
import math

import trio
import chess

from noobchessdbpy.library import AsyncCDBLibrary, BreadthFirstState, CDBArgs

logging.basicConfig(
    format="%(levelname)s [%(asctime)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO
)

########################################################################################################################

async def query_bfs(args):
    print(f"maxply={args.ply}, count={args.count}")
    async with AsyncCDBLibrary(args=args) as lib:
        results = await lib.query_breadth_first(BreadthFirstState(args.fen), maxply=args.ply, count=args.count)
    return results

def main(args):
    if not args.count and not args.ply and not args.infinite:
        parser.error("at least one of the limits is required (see --help)")
    elif args.infinite and (args.count or args.ply):
        parser.error("cannot have limits and --infinite (see --help)")
    if args.count is None:
        args.count = math.inf
    if args.ply is None:
        args.ply = math.inf

    results = trio.run(query_bfs, args)
    #results = {b.fen(): j for b, j in results}
    #for res in results:
    #    print(res['moves'][0:2])
    # the user may write whatever processing of interest here
    if args.output:
        print(f"writing to {args.output}...")
        # raw json probably isn't terribly legible on its own
        with open(args.output, 'w') as handle:
            handle.write('\n'.join(f"{b.fen()}\n{j}" for b, j in results) + '\n')
    print("complete")

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)

limits = parser.add_argument_group('limits', 'breadth-first limits, at least one of these is required:')
CDBArgs.LimitCount.add_to_parser(limits, default=None)
CDBArgs.PlyMax.add_to_parser(limits, default=None)
limits.add_argument('-i', '--infinite', action='store_true', help='unlimited querying')

CDBArgs.add_args_to_parser(parser, (CDBArgs.Fen, CDBArgs.OutputFilename))
CDBArgs.add_api_args_to_parser(parser)

if __name__ == '__main__':
    args = parser.parse_args()
    main(args)
