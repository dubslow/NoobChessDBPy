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
import chess.pgn

import logging
import math

logging.basicConfig(
    format="%(levelname)s [%(asctime)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO
)

async def parse_and_queue_pgn(filename, start=0, count=math.inf):
    if start:
        start = int(start)
    if count is not math.inf:
        count = int(count)

    async with AsyncCDBLibrary() as lib:
        with open(filename) as filehandle:
            #all_positions = lib.parse_pgn(filehandle, start=100, count=100)
            all_positions = lib.parse_pgn(filehandle, start, count)
        n = len(all_positions)
        print(f"now mass queueing {n} positions")
        await lib.mass_queue(all_positions)
        print(f"all {n} positions have been queued for analysis")


if __name__ == '__main__':
    from sys import argv
    args = argv[1:]
    if not args:
        raise ValueError('args: filename [start] [count] (optionally skip `start` games and process not more than `count`)')
    trio.run(parse_and_queue_pgn, *args)
