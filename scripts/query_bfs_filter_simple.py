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
Query positions in breadth first order, filter them by an arbitrary predicate, and write the accepted positions to file.

This "simple" version uses a batching process: query a batch of positions, then filter the batch, then query another
batch, etc, until the given limits are reached. (One or more limit arguments are required, see below.)

As a baseline, this script includes a default, example filter called `well_biased_filter`. `well_biased_filter` accepts
knife-edge positions with at least two viable moves.

Users are encouraged to write any other filter they desire. Many more advanced filters are possible based on CDB's
query-response data.

Be warned that the output isn't immediately suitable for book building: no checks are done for transpostions or multiple
hits in a single PV or similar. Such variety checks should be applied before making a book proper.

Being a "brute force" breadth-first iterator, the positions produced will have been reached by blunders, on average --
but blunders that average out to passing the filter.

Finally, for root positions other than the startpos, CDB is likely to not know most of these blundering positions.
Therefore, running a non-startpos query twice, the second a day after the first, is likely to produce more filtered
positions, after the CDB elves have processed the formerly-unknown blunder positions.
'''

import argparse
import logging
import math

import trio
import chess

from noobchessdbpy.api import CDBStatus
from noobchessdbpy.library import AsyncCDBLibrary, BreadthFirstState, CDBArgs

logging.basicConfig(
    format="%(levelname)s [%(asctime)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO
)


def well_biased_filter(board:chess.Board, cdb_json):
    '''Given a CDB json response for a position, filter for well-biased positions, meaning:
    a position whose top two moves are in the range [90, 112]'''
    # Refer to AsyncCDBClient.query_all docstring, or the CDB website, for a quick format reference.
    # Note that we don't actually use the `board` arg here, but ofc some may find use for it
    if cdb_json['status'] is not CDBStatus.Success:
        return False
    moves = cdb_json['moves']
    if len(moves) < 5: return False # Guarantee some minimum quality of analysis
    t1, t2 = moves[0:2]
    # don't filter captures by default, but it's a small example of what's possible with cdb data
    #if 'x' in t1['san'] or 'x' in t2['san']: return False
    cp1, cp2 = t1['score'], t2['score']
    return 90 <= abs(cp1) <= 112 and 90 <= abs(cp2) <= 112
    # one might also consider cdb's "winrate" thingy, 35 <= winrate <= 65 or smth

def well_biased_filter_formatter(board:chess.Board, cdb_json):
    '''Corresponding to some filter, format the relevant data into a string for output'''
    return f"{cdb_json['moves'][0]['score']:>4} {cdb_json['moves'][1]['score']:>4} {board.fen()}"


async def query_bfs_filter_simple(args):
    '''Using any filter, query breadth-first for positions which pass the filter.'''
    async with AsyncCDBLibrary(args=args) as lib:
        filtered_poss = await lib.query_bfs_filter_simple(args.fen, well_biased_filter, args.target,
                                                          args.ply, args.count, args.batchsize)
    return filtered_poss

def main(args):
    if not args.count and not args.ply and not args.target:
        parser.error("at least one of the limits is required (see --help)")
    if args.count is None:
        args.count = math.inf
    if args.ply is None:
        args.ply = math.inf
    if args.target is None:
        args.target = math.inf

    filtered_poss = trio.run(query_bfs_filter_simple, args)

    if args.output:
        print(f"writing to {args.output}...")
        with open(args.output, 'w') as handle:
            handle.write('\n'.join(well_biased_filter_formatter(board, json) for board, json in filtered_poss) + '\n')
    print("complete")

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)


limits = parser.add_argument_group('limits', 'breadth-first limits, at least one of these is required:')
CDBArgs.LimitCount.add_to_parser(limits, default=None,
                                         help='the maximum number of positions to query (rounded to batchsize)')
CDBArgs.PlyMax.add_to_parser(limits, default=None)
limits.add_argument('-t', '--target', type=int, help='stop after the target number of positions passing the filter')


parser.add_argument('-b', '--batchsize', type=int,
                    help='this many queries between each filtering (default: a multiple of concurrency)')
CDBArgs.add_args_to_parser(parser, CDBArgs.Fen, CDBArgs.OutputFilename)
CDBArgs.add_api_args_to_parser(parser)

if __name__ == '__main__':
    args = parser.parse_args()
    main(args)
