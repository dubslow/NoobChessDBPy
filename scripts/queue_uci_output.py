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
reads a list of `info depth ... pv ucimove ucimove ucimove ...` from a list of files for mass queueing, after deduplicating

(doesn't read fen from the `position` command.... TODO)

to paste just one such line into a command, see queue_fen_uci.py; if you have PGN files, see queue_pgn.py
'''

import argparse
import logging
from typing import Iterable

import chess.pgn
import trio

from noobchessdbpy.library import AsyncCDBClient, AsyncCDBLibrary

logging.basicConfig(
    format="%(levelname)s [%(asctime)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO
)


def read_one_file_uci(filename):
    '''yield lists of ucimoves, one per `info depth` line'''
    with open(filename) as handle:
        for line in handle:
            if line.startswith('info depth'):
                moves = line.split(' pv ')[1]
                yield moves.split()

def parse_fen_uci(board:chess.Board, ucimoves:Iterable[str]) -> list[chess.Board]:
    '''given a board and a list of ucimove strings, parse into a list of `chess.Board`s'''
    board = board.copy(stack=False)
    yield board
    for uci in ucimoves:
        board.push_uci(uci)
        yield board.copy(stack=False)

async def mass_queue_uci(args):
    fens = set()
    # this fen -> chess.Board -> fen cycle remains quite expensive...
    n = 0
    print(f"reading from {args.filenames} ...")
    for fname in args.filenames:
        for line in read_one_file_uci(fname):
            boards = list(parse_fen_uci(args.fen, line))
            n += len(boards)
            fens.update(board.fen() for board in boards)
    print(f"found {n} positions of which {len(fens)} are unique, queueing...")
    async with AsyncCDBLibrary(concurrency=args.concurrency) as lib, trio.open_nursery() as nursery:
        await lib.mass_queue_set(fens)
    print("complete")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('filenames', nargs='+', help="A list of filenames to read UCI output from.")
    parser.add_argument('-f', '--fen', type=chess.Board, default=chess.Board(),
                            help="the FEN which is the root of the PV lines in the files (default: classical startpos)")
    parser.add_argument('-c', '--concurrency', type=int, default=AsyncCDBClient.DefaultConcurrency,
                                                      help="maximum number of parallel requests (default: %(default)s)")
    args = parser.parse_args()
    trio.run(mass_queue_uci, args)
