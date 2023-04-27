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
parses "fen san san san" directly from cmdline args, no string quoting required
useful for pasting ad hoc fen + san inputs, e.g. sesse output

if you already have pgn, try pasting it to queue_single_line.py
                          or reading it from file with parse_and_queue_pgn.py
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


def parse_fen_san(args) -> str:
    '''
    parses "fen san san san" directly from cmdline args
    returns limited pgnstr for parsing by `chess.pgn`
    useful for pasting ad hoc fen + san inputs, e.g. sesse output
    '''
    fen = ' '.join(args[:6])
    args = args[6:]
    return f'''[FEN "{fen}"]\n''' + ' '.join(args)

async def queue_line(args):
    pgnstr = parse_fen_san(args)
    pgn = chess.pgn.read_game(StringIO(pgnstr))
    print(f"parsed {len(list(pgn.mainline()))} moves from cmdline")
    async with AsyncCDBLibrary() as lib:
        await lib.queue_single_line(pgn)


if __name__ == '__main__':
    from sys import argv
    args = argv[1:]
    if not args:
        raise ValueError('pass some FEN dumbdumb')
    trio.run(queue_line, args)
