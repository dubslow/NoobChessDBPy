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
import chess.pgn
from io import StringIO
import logging

logging.basicConfig(
    format="%(levelname)s [%(asctime)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO
)


async def queue_and_query_single_line(args, time=29):
    '''Probably this function is of not-so-great utility, as the requisite waiting time for reverse-querying to be useful
    is highly variable and frequently more than a minute. Best stick with just the queue instead.

    (Otherwise, the core idea is that, after queuing for analysis, sometimes CDB doesn't immediately connect all the moves
    and positions together, impeding backpropagation of leaf scores to their parents. Querying in reverse order can
    sometimes hasten connections and backpropagation, however in any case the connections are always made within a day
    or two by CDB backend tree-integrity processes.)'''
    async with AsyncCDBLibrary() as lib, trio.open_nursery() as nursery:
        games = []
        for arg in args:
            game = chess.pgn.read_game(StringIO(arg))
            games.append(game)
            print("queuing game...")
            nursery.start_soon(lib.queue_single_line, game)
        print(f"queued all games, waiting for {time=}...")
        await trio.sleep(time) # 10? 30? 60? how long do queues take lol (default timing based on only 1 arg)
        print("waited, now reverse querying the games...")
        for game in games:
            print("reverse querying game...")
            nursery.start_soon(lib.query_reverse_single_line, game)


if __name__ == '__main__':
    from sys import argv
    args = argv[1:]
    if not args:
        raise ValueError('pass some FEN dumbdumb')
    trio.run(queue_and_query_single_line, args, 61)
