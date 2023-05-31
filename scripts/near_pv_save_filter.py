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
iterate over CDB near PVs, using a filtering visitor to search for particular kinds of positions. The example filter
in this script looks for positions whose two best moves have "knife-edge" well-biased scores, to decrease drawrate.
Users are of course encouraged to customize the filter or the formatting to file as they please.

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

async def iterate_near_pv_visitor_save_filter(client, circular_requesters, board, result, margin, relply, maxply):
    '''
    This is a Near PV visitor: pass it to `iterate_near_pv` to return, and thus save, positions which pass the filter.
    In this case, looking for top two moves to both have well-biased scores.
    (This particular visitor ignores most of its arguments.) See `help(iterate_near_pv)` for details of the visitor
    interface.
    '''
    # This is pretty much copied from query_bfs_filter_simple.py lol
    # Refer to AsyncCDBClient.query_all docstring, or the CDB website, for a quick format reference.
    # Note that we don't actually use the `board` arg here, but ofc some may find use for it
    if result['status'] is not CDBStatus.Success:
        return
    moves = result['moves']
    if len(moves) < 5: return # Guarantee some minimum quality of analysis
    t1, t2 = moves[0:2]
    # don't filter captures by default, but it's a small example of what's possible with cdb data
    #if 'x' in t1['san'] or 'x' in t2['san']: return False
    cp1, cp2 = t1['score'], t2['score']
    if 80 <= abs(cp1) <= 100 and 80 <= abs(cp2) <= 100:
        return result
    return
    # one might also consider cdb's "winrate" thingy, 35 <= winrate <= 65 or smth

async def iterate_near_pv(args):
    async with AsyncCDBLibrary(args=args) as lib:
        results = await lib.iterate_near_pv(args.fen, iterate_near_pv_visitor_save_filter, args.margin,
                                            margin_decay=args.decay, maxbranch=args.branching, maxply=args.ply,
                                            count=args.count)
    return results


def main(args):
    # user can write any post-processing they like here
    results = trio.run(iterate_near_pv, args)
    if args.output:
        print(f"writing to {args.output}...")
        # for the filter above, we cut most of the results data, printing only top 5 moves and their score
        results_formatter = lambda result: {move['san']: move['score'] for move in result['moves'][:3]}
        with open(args.output, 'w') as f:
            f.write('{\n' + '\n'.join(f'''"{key}": {results_formatter(val)}''' for key, val in results.items()) + '\n}\n')
        print(f"wrote to {args.output}, all done, now exiting.")


parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
CDBArgs.add_args_to_parser(parser, CDBArgs.Fen, CDBArgs.NearPVMargin, CDBArgs.NearPVDecay, CDBArgs.NearPVBranchMax,
                                   CDBArgs.LimitCount, CDBArgs.PlyMax, CDBArgs.OutputFilename)
CDBArgs.add_api_args_to_parser(parser)

if __name__ == '__main__':
    args = parser.parse_args()
    main(args)
