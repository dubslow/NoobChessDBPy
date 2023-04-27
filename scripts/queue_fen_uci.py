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
parses "fen ucimove ucimove ucimove" directly from cmdline args, no string quoting required
useful for pasting ad hoc fen + ucimove inputs, e.g. your local engine output

if you already have pgn, try pasting it to queue_single_line.py
                          or reading it from file with parse_and_queue_pgn.py

example:

python queue_fen_uci.py 6k1/2B3p1/p1b4p/2b5/P1p1p3/2Nn3P/1PR3PK/8 w - - 5 35 a4a5 g7g5 c2e2 d3c1 e2e1 c1d3 e1f1 c5f2 c7d6 g8g7 d6e5 g7g8 e5c7 f2d4 c7b6 d4e5 h2g1 d3f4 g1f2 h6h5 g2g3 f4d3 f2e3 e5g3 f1f6 c6b7 b6d4 g3f4 e3e2
parsed 30 moves from cmdline
completed 30 queues
'''

from noobchessdbpy.library import AsyncCDBLibrary

import trio
import chess.pgn

from io import StringIO
import logging

logging.basicConfig(
    format="%(levelname)s [%(asctime)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO
)

def parse_fen_uci(args) -> list[chess.Board]:
    '''
    parses "fen ['moves'] ucimove ucimove ucimove" directly from cmdline args (word 'moves' is optional)
    returns list of boards to queue
    useful for pasting engine pv output directly into a queue command
    '''
    fen = ' '.join(args[:6])
    args = args[6:]
    if args[0] == 'moves':
        args = args[1:]
    board = chess.Board(fen=fen)
    lst = [board.copy(stack=False)]
    for uci in args:
        board.push_uci(uci)
        lst.append(board.copy(stack=False))
    return lst

async def queue_line(args):
    line = parse_fen_uci(args)
    print(f"parsed {len(line)} moves from cmdline")
    async with AsyncCDBLibrary() as lib, trio.open_nursery() as nursery:
        n = 0
        for board in line:
            nursery.start_soon(lib.queue, board)
            n += 1
    print(f"completed {n} queues")    


if __name__ == '__main__':
    from sys import argv
    args = argv[1:]
    if not args:
        raise ValueError('pass some FEN dumbdumb')
    trio.run(queue_line, args)
