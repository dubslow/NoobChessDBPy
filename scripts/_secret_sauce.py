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
This script contains super secret sauce that might be necessary to run longer stuff!
'''

import argparse
import time
import trio

from noobchessdbpy.api import AsyncCDBClient, CDBError

async def mittent_clear(periodmins=20, totalmins=17*60):
    async with AsyncCDBClient() as client:
        for i in range(totalmins//periodmins+1):
            print("clearing... ", end='')
            try:
                await client._clear_limit()
            except CDBError: # TODO: change "limit cleared" to not raise
                pass
            print(f"cleared {i}, waiting {periodmins=}...")
            time.sleep(periodmins*60)

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('-p', '--period', type=int, default=15, help='minutes between each clear')
parser.add_argument('-t', '--total', type=float, default=24, help='total number of hours to to clear for')

if __name__ == '__main__':
    args = parser.parse_args()
    trio.run(mittent_clear, args.period, args.total*60)
