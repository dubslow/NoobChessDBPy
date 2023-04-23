#! python3.11

from api import AsyncCDBClient
from library import AsyncCDBLibrary
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


async def analyze_single_line(args):
    async with AsyncCDBLibrary() as lib, trio.open_nursery() as nursery:
        for arg in args:
            nursery.start_soon(lib.analyze_single_line, arg)


if __name__ == '__main__':
    from sys import argv
    args = argv[1:]
    if not args:
        raise ValueError('pass some FEN dumbdumb')
    trio.run(analyze_single_line, args)
