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


async def queue_single_line(args):
    async with AsyncCDBLibrary() as lib, trio.open_nursery() as nursery:
        for arg in args:
            nursery.start_soon(lib.queue_single_line, arg)


if __name__ == '__main__':
    from sys import argv
    args = argv[1:]
    if not args:
        raise ValueError('pass some FEN dumbdumb')
    trio.run(queue_single_line, args)
