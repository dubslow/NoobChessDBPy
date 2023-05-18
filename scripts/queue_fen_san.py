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
useful for pasting ad hoc FEN + SAN inputs, e.g. sesse PV outputs

if you already have pgn, try pasting it to queue_lines.py or reading it from file with queue_pgn.py

example:

python queue_fen_san.py 6k1/2B3p1/p1b4p/2b5/P1p1p3/2Nn3P/1PR3PK/8 w - - 5 35 35. a5 h5 36. Bb6 Be7 37. Kg1 Bf6 38. Re2 Nf4 39. Re1 h4 40. Ne2 g5 41. Nc3 e3 42. Rxe3 Bxg2 43. Ne2 Kf7 44. Nxf4 gxf4 45. Re1 Bxh3 46. Re4 Bxb2 47. Rxf4+ Ke6 48. Rxc4 Kd5 49. Rxh4 Bd7 50. Kf2 Bf6 51. Rh6 Bb2 52. Rh7 Bb5 53. Rh4 Bf6 54. Rf4 Bb2 55. Kf3 Bg7 56. Rf7 Bb2 57. Rc7 Ba3 58. Rc8 Bb4 59. Ke3 Ba3 60. Kd2 Bd7
parsed 52 positions from cmdline
completed 52 queues
'''

import argparse
from io import StringIO
import logging

import chess.pgn
import trio

from noobchessdbpy.library import AsyncCDBLibrary, CDBArgs

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

async def queue_line(args, pgn):
    async with AsyncCDBLibrary(args=args) as lib:
        await lib.queue_single_line(pgn)

def main(args):
    pgnstr = parse_fen_san(args.fen_and_moves)
    pgn = chess.pgn.read_game(StringIO(pgnstr))
    print(f"parsed {len(list(pgn.mainline()))} positions from cmdline")
    trio.run(queue_line, args, pgn)

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('fen_and_moves', nargs='+', help="fen and SAN moves (unquoted)")
CDBArgs.add_api_flat_args_to_parser(parser)

if __name__ == '__main__':
    args = parser.parse_args()
    main(args)
