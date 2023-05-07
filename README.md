## CDB Python API

A currently-skeletal python interface to CDB using async+trio.

CDB is this: https://www.chessdb.cn/queryc_en/ altho it goes by so many names that the package name is longer for
unambiguity. Nevertheless in context it shall simply be called CDB. It is maintained here:
https://github.com/noobpwnftw/chessdb

The two basic actions on CDB are "query" and "queue". A query is a read-op, requesting information, moves, scores, on
a given position, whatever the db already knows. A queue is a write-op, requesting for the CDB backend to store a given
position, and run some initial analysis for storage. (Queueing already-known positions results in the backend refreshing
child nodes, re-backprogating new scores and other info.)

See `scripts/` and docstrings therein for basic usage examples, together with `help()` on the imports demonstrated therein.
For queries, a basic "query args" script is given, as well as slightly fancier "mass query breadth first" type stuff.
For queues, there's several basic examples of pasting various formats into commandline args in various ways, or reading
positions from PGN files for mass queuing.

No promises of utility. Feedback welcome, via this repo or Stockfish Discord.

Can be used in the ~standard python way:

```
mkdir ~/noobchessdbpy
cd ~/noobchessdbpy

git clone https://github.com/dubslow/NoobChessDBPy.git .

# make and use virtualenv
python3 -m venv venv --prompt .
source venv/bin/activate
pip install -r requirements.txt

# now try some example scripts
cd scripts
python queue_single_line.py $'1. e4 c6 2. Nf3 d5 3. Nc3 Nf6 4. e5 Ne4 5. Ne2 Bf5 6. Nfd4 e6 7. Nxf5 exf5 8. c3 Nd7 9. d4 Be7 10. Qb3 O-O 11. f3 Ng5 12. Qxb7 Rc8 13. Nf4 Ne6 14. Be2 a5 15. Qb3 g5 16. Nxe6
*'
# that starts analysis of every position in that line. the $' ' shell quoting allows
# longform pgn with newlines to be quoted into a single shell arg
```
