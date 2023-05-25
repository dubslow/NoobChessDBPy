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
iterate over CDB near PVs, using a "save all" visitor to record results of all known positions traversed.
Users are of course encouraged to customize the visitor or the formatting to file as they please.

Run this command for more details about the walking:
`python -c "from noobchessdbpy.library import AsyncCDBLibrary; help(AsyncCDBLibrary.iterate_near_pv)"`

Note: fortresses quickly cause search explosions. Changing the margin by a single cp may cause the iterator to hit a
fortress, or indeed the same margin used multiple times in a row may cause the (near-)PV to shift towards one (or away
from one).

------------------------------------------------------

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

from noobchessdbpy.api import CDBStatus
from noobchessdbpy.library import AsyncCDBLibrary, CDBArgs

logging.basicConfig(
    format="%(levelname)s [%(asctime)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO
)

########################################################################################################################

async def iterate_near_pv_visitor_save_all(client, circular_requesters, board, result, margin, relply, maxply):
    '''
    This is a Near PV visitor: pass it to `iterate_near_pv` to return, and thus save, any known position seen by the
    iterator.
    (This particular visitor ignores most of its arguments.) See `help(iterate_near_pv)` for details of the visitor
    interface.
    '''
    if result['status'] is CDBStatus.Success:
        return result
    return # no data when not a known position (or bad request in some way)

async def iterate_near_pv(args):
    async with AsyncCDBLibrary(args=args) as lib:
        results = await lib.iterate_near_pv(args.fen, iterate_near_pv_visitor_save_all, args.margin,
                                            margin_decay=args.decay, maxbranch=args.branching, maxply=args.ply)
    return results


def main(args):
    # user can write any post-processing they like here
    results = trio.run(iterate_near_pv, args)
    if args.output:
        print(f"writing to {args.output}...")
        with open(args.output, 'w') as f:
            # a pretty basic formatting, simply printing a dict of {fen: cdb_results}. users may desire to reduce the
            # cdb_results data somewhat for their own purposes.
            f.write('{\n' + '\n'.join(f'''"{key}": {val}''' for key, val in results.items()) + '\n}\n')
        print(f"wrote to {args.output}, all done, now exiting.")


parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
CDBArgs.add_args_to_parser(parser, CDBArgs.Fen, CDBArgs.NearPVMargin, CDBArgs.NearPVDecay, CDBArgs.NearPVBranchMax,
                                   CDBArgs.PlyMax, CDBArgs.OutputFilename)
CDBArgs.add_api_args_to_parser(parser)

if __name__ == '__main__':
    args = parser.parse_args()
    main(args)
