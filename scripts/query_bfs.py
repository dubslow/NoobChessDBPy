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
At the moment this doesn't do much useful stuff. What it does is queries positions breadth first, returning the
moves-results from CDB. More of a demonstration/example than independently useful, as yet.
'''

from noobchessdbpy.api import AsyncCDBClient
from noobchessdbpy.library import AsyncCDBLibrary, BreadthFirstState

import trio
import chess

import logging

logging.basicConfig(
    format="%(levelname)s [%(asctime)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO
)


async def query_bfs():
    rootpos = chess.Board()
    async with AsyncCDBLibrary() as lib:
        count, concurrency = 20, 256
        print(f"{count=} {concurrency=}")
        results = await lib.query_breadth_first(BreadthFirstState(rootpos), count=count, concurrency=concurrency)
    #for res in results:
    #    print(res['moves'][0:2])
        


if __name__ == '__main__':
#    from sys import argv
#    args = argv[1:]
#    if not args:
#        raise ValueError('pass some FEN dumbdumb')
    trio.run(query_bfs)#, args)
