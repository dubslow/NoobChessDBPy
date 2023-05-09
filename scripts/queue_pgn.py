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
This script reads PGN games directly from command line arguments, and mass-queues whatever it sees in parallel.

PGN games can be pasted into a single argument by using bash's multiline string quoting syntax:

$'this is
a multiline
single arg'

(see e.g. https://stackoverflow.com/a/25941527/1497645)

This is useful for e.g. pasting TCEC PVs (players or kibitzers) for queueing. One can paste the game moves, two players'
PV pgn and two kibitzers' PV pgn, for a total of 5 arguments to this script, which will all be queued in parallel (less
than a second for hundreds of positions). In other words, live TCEC data can be queued into CDB just as fast as you can
copy and paste it. (To queue from files, see parse_and_queue_pgn.py.)
'''

import argparse
from io import StringIO
import logging

import chess
import chess.pgn
import trio

from noobchessdbpy.api import AsyncCDBClient
from noobchessdbpy.library import AsyncCDBLibrary

logging.basicConfig(
    format="%(levelname)s [%(asctime)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO
)


async def queue_single_line(args):
    async with AsyncCDBLibrary() as lib, trio.open_nursery() as nursery:
        #print("initialized client and outer nursery")
        for i, arg in enumerate(args.pgns):
            game = chess.pgn.read_game(StringIO(arg))
            print(f"starting queue-tasks for line {i}...")
            nursery.start_soon(lib.queue_single_line, game)
        #print("all lines begun...")
    print("all queues complete")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('pgns', nargs='+',
                help="a set of pasted PGN games to queue. Use bash $'' quoting to enable a multi-line single argument.")
    args = parser.parse_args()
    trio.run(queue_single_line, args)
