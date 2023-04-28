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
Query positions in breadth first order, subject to a filter, and write the positions to file.
This can of course easily be expanded to do whatever more analysis the user likes on the positions.
Configure the defaults by modifying the all capital globals below.

Note that no checking for transpositions or one good pos being the child of another is done. Users
shouldn't directly construct a book from this, but should do further filtering for variety.
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


from sys import argv
OUT_FILE  = argv[0].replace('.py', '.txt')
BASEPOS   = chess.Board() # classical startpos, can also put FEN here
TARGET    = 200
CHUNKSIZE = 1024

def predicate(board:chess.Board, cdb_json):
    '''Given a CDB json response for a position, filter for well-biased positions'''
    # Refer to AsyncCDBClient.query_all docstring for a quick format reference.
    # Note that we don't actually use the `board` arg here, but ofc some may find use for it
    moves = cdb_json['moves']
    top_move = moves[0]
    cp_score = top_move['score']
    return 90 <= abs(cp_score) <= 112
    # one might also consider cdb's "winrate" thingy, 35 <= winrate <= 65 or smth


async def query_bfs_filter_simple():
    async with AsyncCDBLibrary() as lib:
        filtered_poss = await lib.query_bfs_filter_simple(BASEPOS, predicate, TARGET, chunksize=CHUNKSIZE)
    print(f"now have {len(filtered_poss)} positions, writing to {OUT_FILE}...")
    with open(OUT_FILE, 'w') as handle:
        handle.write('\n'.join(f"{json['moves'][0]['score']} {board.fen()}" for board, json in filtered_poss) + '\n')
    print("complete")

if __name__ == '__main__':
    trio.run(query_bfs_filter_simple)
