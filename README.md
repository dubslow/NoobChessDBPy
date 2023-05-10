## CDB Python API

A currently-skeletal python interface to CDB using async+trio.

CDB is this: https://www.chessdb.cn/queryc_en/ altho it goes by so many names that the package name is longer for
unambiguity. Nevertheless in context it shall simply be called CDB. It is maintained here:
https://github.com/noobpwnftw/chessdb

The two basic actions on CDB are "query" and "queue". A query is a read-op, requesting information, moves, scores, on
a given position, whatever the db already knows (altho typically, as a side effect, a query for an unknown position will
cause that position to become stored). A queue is a write-op: for an unknown board, it requests for the CDB
backend to run some initial analysis for storage as a known position. Queueing is recursive: for already-known positions, it extends
PV lines, implying more work is done for queuing near-root positions than near-leaf positions.

See `scripts/` and docstrings therein for basic usage examples, together with `help()` on the imports demonstrated therein.
All scripts have a `--help` option explaining its purpose. All code (script or package) is meant to be readable and
well-documented, and users are encouraged to write their own scripts (in addition to using the included scripts).

At the present time, the scripts are loosely separated into querying scripts vs queueing scripts. For querying there's
a basic "paste FEN into command line" skeleton example, as well as some breadth-first style mass-querying of a couple
types. For queuing, there's scripts to read PGN files, or to paste into the command line PGN, uci output, or SAN.


No promises of utility, altho I certainly hope it is. Feedback welcome, via this repo or Stockfish Discord.

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
python query_fens.py --help
python queue_lines.py --help
python queue_pgn.py --help

# example commands
python queue_fen_san.py 6k1/2B3p1/p1b4p/2b5/P1p1p3/2Nn3P/1PR3PK/8 w - - 5 35 35. a5 h5 36. Bb6 Be7 37. Kg1 Bf6 38. Re2 Nf4 39. Re1 h4 40. Ne2 g5 41. Nc3 e3 42. Rxe3 Bxg2 43. Ne2 Kf7 44. Nxf4 gxf4 45. Re1 Bxh3 46. Re4 Bxb2 47. Rxf4+ Ke6 48. Rxc4 Kd5 49. Rxh4 Bd7 50. Kf2 Bf6 51. Rh6 Bb2 52. Rh7 Bb5 53. Rh4 Bf6 54. Rf4 Bb2 55. Kf3 Bg7 56. Rf7 Bb2 57. Rc7 Ba3 58. Rc8 Bb4 59. Ke3 Ba3 60. Kd2 Bd7
python queue_fen_uci.py 6k1/2B3p1/p1b4p/2b5/P1p1p3/2Nn3P/1PR3PK/8 w - - 5 35 a4a5 g7g5 c2e2 d3c1 e2e1 c1d3 e1f1 c5f2 c7d6 g8g7 d6e5 g7g8 e5c7 f2d4 c7b6 d4e5 h2g1 d3f4 g1f2 h6h5 g2g3 f4d3 f2e3 e5g3 f1f6 c6b7 b6d4 g3f4 e3e2


python queue_lines.py $'1. e4 c6 2. Nf3 d5 3. Nc3 Nf6 4. e5 Ne4 5. Ne2 Bf5 6. Nfd4 e6 7. Nxf5 exf5 8. c3 Nd7 9. d4 Be7 10. Qb3 O-O 11. f3 Ng5 12. Qxb7 Rc8 13. Nf4 Ne6 14. Be2 a5 15. Qb3 g5 16. Nxe6
*'
# the $' ' shell quoting allows longform pgn with newlines, including headers, to be quoted into a single shell arg

python queue_pgn.py TCEC_Season_24_-_Division_P.pgn
```
