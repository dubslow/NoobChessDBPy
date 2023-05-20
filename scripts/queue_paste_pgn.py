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
This script reads games directly from command line arguments, and mass-queues the main line concurrently.

PGN/SAN can be pasted into a single argument by using bash's multiline string quoting syntax:

$'this is
a multiline
single arg'

(see e.g. https://stackoverflow.com/a/25941527)

Pasting SAN alone works, and is assumed to be from the startpos. Pasting PGN headers also works, including non-startpos
positions from which to read SAN (such as in TCEC PVs copied out of the TCEC GUI).

This is useful for e.g. pasting TCEC PVs (players or kibitzers) for queueing. One can paste the game moves, the two
players' PV pgn and the two kibitzers' PV pgn, for a total of 5 arguments to this script, which will all be queued in
parallel (less than a second for hundreds of positions). In other words, live TCEC data can be queued into CDB just as
fast as you can copy and paste it.

To queue all variations, or else to queue from a PGN file, see queue_pgn.py.
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


async def queue_single_line(args):
    async with AsyncCDBLibrary(args=args) as lib, trio.open_nursery() as nursery:
        #print("initialized client and outer nursery")
        for i, arg in enumerate(args.pgns):
            game = chess.pgn.read_game(StringIO(arg))
            print(f"starting queue-tasks for line {i}...")
            nursery.start_soon(lib.queue_single_line, game)
        #print("all lines begun...")
    print("all queues complete")

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('pgns', nargs='+',
               help="a set of pasted lines (PGN) to queue. Use bash $'' quoting to enable a multiline single argument.")
CDBArgs.add_api_flat_args_to_parser(parser)

if __name__ == '__main__':
    args = parser.parse_args()
    trio.run(queue_single_line, args)
