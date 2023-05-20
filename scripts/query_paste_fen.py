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
This script demonstrates the most basic usage of the API, simply querying each FEN arg.

For example:
python query_fens.py "rnbq1bnr/pppkpppp/3p4/8/1P6/3P1P2/P1P1P1PP/RNBQKBNR b KQ - 0 3" "8/6k1/R7/1r5P/5PK1/8/8/8 w - - 0 1" "rnbqkb1r/ppp1pp1p/3p1np1/8/3PPP2/2N5/PPP3PP/R1BQKBNR b KQkq - 0 1"

To query FENs from files, see query_files_fen.py
'''

import argparse
import logging
from sys import stdout

import chess
import trio

from noobchessdbpy.api import AsyncCDBClient
from noobchessdbpy.library import CDBArgs

logging.basicConfig(
    format="%(levelname)s [%(asctime)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO
)

fancy_board = lambda board: board.unicode() if stdout.encoding.startswith('utf') else str(board)

async def process_fen(client, board):
    json = await client.query_all(board)
    # call_my_fancy_processing(board, json)
    print(f"for board:\n{fancy_board(board)}\ngot moves:\n"
          f"""{", ".join(f"{move['san']}={move['score']}" for move in json['moves'])}\n""")

async def query_fens(args):
    async with AsyncCDBClient(args=args) as client, trio.open_nursery() as nursery:
        for board in args.fens:
            #print(f'spawning for {arg}')
            nursery.start_soon(process_fen, client, board)

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('fens', nargs='+', type=CDBArgs.Fen.value[1]['type'], help="a list of FENs to query")
CDBArgs.add_api_flat_args_to_parser(parser)

if __name__ == '__main__':
    args = parser.parse_args()
    trio.run(query_fens, args)
