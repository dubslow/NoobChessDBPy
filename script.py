#! python3.11

from api import AsyncCDBClient
import trio
import chess
import logging

logging.basicConfig(
    format="%(levelname)s [%(asctime)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.DEBUG
)

async def process_query_all(client, arg):
    #print(f"making Board for {arg}")
    board = chess.Board(arg)
    text = await client.query_all_known_moves(board)
    print(f'for board:\n{board.unicode()}\ngot moves:\n{text}')


async def main(args):
    async with AsyncCDBClient() as client, trio.open_nursery() as nursery:
        for arg in args:
            #print(f'spawning for {arg}')
            nursery.start_soon(process_query_all, client, arg)

if __name__ == '__main__':
    from sys import argv
    args = argv[1:]
    if not args:
        raise ValueError('pass some FEN dumbdumb')
    trio.run(main, args)
