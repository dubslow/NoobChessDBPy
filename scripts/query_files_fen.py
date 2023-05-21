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
Given a list of filenames, read (line-separated) FENs and write to output some result data about each FEN.
'''

import argparse

import chess
import trio

from noobchessdbpy.api import strip_fen, CDBStatus
from noobchessdbpy.library import AsyncCDBLibrary, CDBArgs

# a lot of this code is in common with parse_pgn(), queue_files_pgn.py, and query_bfs*.py

def read_file(handle):
    print(f"reading {handle.name}...")
    out_dict = {}
    x = 0
    for line in handle:
        x += 1
        fen = strip_fen(line)
        #board = chess.Board(fen)
        out_dict[fen] = None
    print(f"found {x} lines, {len(out_dict)} fens")
    return out_dict, x

def parse_fens(args):
    # this is more or less copy-pasted from queue_files_pgn.py
    all_positions, n, u_sub = dict(), 0, 0
    for i, filename in enumerate(args.filenames):
        with open(filename) as filehandle:
            this_positions, x = read_file(filehandle)
        n += x
        u_sub += len(this_positions)
        all_positions |= this_positions
        u = len(all_positions)
        if i > 0:
            print(f"after cross-deduplication, found {u} cross-unique positions from {u_sub} sub-unique from {n} "
                  f"total, {u/n if n else math.nan:.2%} unique rate")
    return all_positions

async def mass_query_dict(args, fen_dict):
    async with AsyncCDBLibrary(args=args) as lib:
        tuples = await lib.mass_query_fens(fen_dict.keys())
    for board, results in tuples:
        fen = strip_fen(board.fen())
        fen_dict[fen] = results

def results_formatter(fen, results):
    if results is not None and results['status'] is CDBStatus.Success:
        moves = results['moves']
        return f"{fen}  score={moves[0]['score']} " f'''{" ".join(f"{move['san']}={move['score']}" for move in moves[:3])}'''
    else:
        return f"{fen} {results}"

def write_results(args, fen_dict):
    if args.output:
        print(f"writing to {args.output}...")
        with open(args.output, 'w') as handle:
            handle.write('\n'.join(results_formatter(fen, results) for fen, results in fen_dict.items()) + '\n')

def main(args):
    print(f"got names: {args.filenames}")
    fen_dict = parse_fens(args)
    trio.run(mass_query_dict, args, fen_dict)
    write_results(args, fen_dict)
    print("complete")


parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('filenames', nargs='+', help="A list of filenames to read FEN from")
CDBArgs.OutputFilename.add_to_parser(parser)
CDBArgs.add_api_args_to_parser(parser)

if __name__ == '__main__':
    args = parser.parse_args()
    main(args)
