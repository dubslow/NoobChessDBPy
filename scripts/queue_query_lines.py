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
Usage like queue_lines.py (e.g. pasting TCEC PVs) except also queries the lines after queuing them.
Almost entirely useless.
'''

import argparse
from io import StringIO
import logging

import chess
import chess.pgn
import trio

from noobchessdbpy.library import AsyncCDBLibrary, CDBArgs

logging.basicConfig(
    format="%(levelname)s [%(asctime)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO
)


async def queue_and_query_lines(args, time=30):
    '''
    Probably this function is of not-so-great utility, as the requisite waiting time for reverse-querying to be useful
    is highly variable and frequently more than a minute. Best stick with just the queue instead.

    (Otherwise, the core idea is that, after queuing for analysis, sometimes CDB doesn't immediately connect all the moves
    and positions together, impeding backpropagation of leaf scores to their parents. Querying in reverse order can
    sometimes hasten connections and backpropagation, however in any case the connections are always made within a day
    or two by CDB backend tree-integrity processes.)
    '''
    async with AsyncCDBLibrary(user=args.user) as lib, trio.open_nursery() as nursery:
        games = []
        for arg in args.pgns:
            game = chess.pgn.read_game(StringIO(arg))
            games.append(game)
            print("queuing line...")
            nursery.start_soon(lib.queue_single_line, game)
        print(f"queued all lines, waiting for {time}s...")
        await trio.sleep(time) # 10? 30? 60? how long do queues take lol (default timing is Client timeout)
        print("waited, now reverse querying the lines...")
        for game in games:
            print("reverse querying line...")
            nursery.start_soon(lib.query_reverse_single_line, game)


parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('pgns', nargs='+',
               help="a set of pasted lines (PGN) to queue. Use bash $'' quoting to enable a multiline single argument.")
CDBArgs.add_api_flat_args_to_parser(parser)

if __name__ == '__main__':
    args = parser.parse_args()
    trio.run(queue_and_query_lines, args)
