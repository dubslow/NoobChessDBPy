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

from noobchessdbpy.api import AsyncCDBClient
from noobchessdbpy.library import AsyncCDBLibrary
import trio
import chess
import logging

logging.basicConfig(
    format="%(levelname)s [%(asctime)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO
)


async def process_query_all(client, arg):
    #print(f"making Board for {arg}")
    board = chess.Board(arg)
    text = await client.query_all(board)
    print(f'for board:\n{board.unicode()}\ngot moves:\n{text}')

async def query_all(args):
    async with AsyncCDBClient() as client, trio.open_nursery() as nursery:
        for arg in args:
            #print(f'spawning for {arg}')
            nursery.start_soon(process_query_all, client, arg)


if __name__ == '__main__':
    from sys import argv
    args = argv[1:]
    if not args:
        raise ValueError('pass some FEN dumbdumb')
    trio.run(query_all, args)
