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
iterate over CDB near PVs, using a "queue any" visitor to `queue` everything seen.

See this for more details about the walking:
`python -c "from noobchessdbpy.library import AsyncCDBLibrary; help(AsyncCDBLibrary.iterate_near_pv)"`

Note: fortresses quickly cause search explosions. Changing the margin by a single cp may cause the iterator to hit a
fortress, or indeed the same margin used multiple times in a row may cause the (near-)PV to shift towards one (or away
from one).

Here, "fortress" means "a position where many moves are all nearly equally best", which causes intense branching and
combinatorial explosion.

Common warning signs for fortresses, loosely in order of utility:
1) when `todo` increases as fast as `nodes` does
2) when `dups` increases as fast as `todo` does (more transpositions than novel nodes)
3) when `todo` approaches the same magnitude as `nodes`
4) when `dups` approaches the magnitude of `nodes`
5) when `relply` remains depressed lower than in previous similar runs
6) when a position has more than 6-8 moves already known (least useful)

TODO: add maxply, fortress-detecting options
'''

import argparse
import logging
import math

import trio
import chess.pgn

from noobchessdbpy.api import AsyncCDBClient
from noobchessdbpy.library import AsyncCDBLibrary, CDBArgs

logging.basicConfig(
    format="%(levelname)s [%(asctime)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO
)

async def iterate_near_pv(args):
    async with AsyncCDBLibrary(concurrency=args.concurrency, user=args.user) as lib:
        results = await lib.iterate_near_pv(args.fen, lib.iterate_near_pv_visitor_queue_any, args.margin,
                                            margin_decay=args.decay, maxbranch=args.branching)
    # user can write any post-processing they like here
    if args.output:
        print(f"writing to {args.output}...")
        with open(args.output, 'w') as f:
            f.write('{\n' + '\n'.join(f'''"{key}": {val}''' for key, val in results.items()) + '\n}\n')
        print(f"wrote to {args.output}, all done, now exiting.")


parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
CDBArgs.Fen.add_to_parser(parser)
parser.add_argument('-m', '--margin', type=int, default=5, choices=range(0, 200), metavar="cp_margin",
                    help="centipawn margin for what's considered near PV (choose from [0,200))")
parser.add_argument('-d', '--decay', '--margin-decay', type=float, default=1.0,
                    help='linear rate per ply by which to shrink the margin (default: %(default)s)')
parser.add_argument('-b', '--branching', '--max-branch', type=int, default=math.inf,
                    help='maximum branch factor at any given node')
CDBArgs.OutputFilename.add_to_parser(parser)
CDBArgs.add_api_args_to_parser(parser)

if __name__ == '__main__':
    args = parser.parse_args()
    trio.run(iterate_near_pv, args)

