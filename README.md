## CDB Python API

A python interface to CDB using async+trio.


##### Intro

CDB is this: https://www.chessdb.cn/queryc_en/ altho it goes by so many names that the package name is longer for
unambiguity. Nevertheless in context it shall simply be called CDB. It is maintained here:
https://github.com/noobpwnftw/chessdb

The two basic actions on CDB are "query" and "queue". A query is a read-op, requesting information, moves, scores, on
a given position, whatever the db already knows (altho typically, as a side effect, a query for an unknown position will
cause that position to become stored). A queue is a write-op: for an unknown board, it requests for the CDB
backend to run some initial analysis for storage as a known position. (On known boards, queue will try to extend the
relevant PVs.)


##### Usage

There are three levels of usage. The simplest is to simply use the scripts included in `scripts/`. They all come with
`--help` options explaining each script's purpose. Each script is intended to do one thing, so there are many scripts to
do many different algorithms relating to CDB.

More advanced usage can be to modify those scripts for some fresh functionality, or otherwise to write your own scripts
by making use of the `noobchessdbpy.library` module. Documentation is meant to be good (altho there will surely always
be room for improvement), and code is meant to be eminently readable. Documentation is available on the docstrings, such
as with `help()`. Try for example `help(noobchessdbpy.library)` or using `help()` on the symbols therein.

Of course one could ignore the included library and instead write your own suite of algorithms directly onto the API.
The API is a fairly thin translation of CDB's API documented here: https://www.chessdb.cn/cloudbookc_api_en.html
See also `help(noobchessdbpy.api)`.

No promises of utility, altho I certainly hope it is. Feedback welcome, via this repo or Stockfish Discord.


##### Installation

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
python query_paste_fen.py --help
python queue_paste_pgn.py --help
python queue_files_pgn.py --help

# example commands
python queue_paste_fen_san.py 6k1/2B3p1/p1b4p/2b5/P1p1p3/2Nn3P/1PR3PK/8 w - - 5 35 35. a5 h5 36. Bb6 Be7 37. Kg1 Bf6 38. Re2 Nf4 39. Re1 h4 40. Ne2 g5 41. Nc3 e3 42. Rxe3 Bxg2 43. Ne2 Kf7 44. Nxf4 gxf4 45. Re1 Bxh3 46. Re4 Bxb2 47. Rxf4+ Ke6 48. Rxc4 Kd5 49. Rxh4 Bd7 50. Kf2 Bf6 51. Rh6 Bb2 52. Rh7 Bb5 53. Rh4 Bf6 54. Rf4 Bb2 55. Kf3 Bg7 56. Rf7 Bb2 57. Rc7 Ba3 58. Rc8 Bb4 59. Ke3 Ba3 60. Kd2 Bd7
python queue_paste_fen_uci.py 6k1/2B3p1/p1b4p/2b5/P1p1p3/2Nn3P/1PR3PK/8 w - - 5 35 a4a5 g7g5 c2e2 d3c1 e2e1 c1d3 e1f1 c5f2 c7d6 g8g7 d6e5 g7g8 e5c7 f2d4 c7b6 d4e5 h2g1 d3f4 g1f2 h6h5 g2g3 f4d3 f2e3 e5g3 f1f6 c6b7 b6d4 g3f4 e3e2

python queue_paste_pgn.py $'1. e4 c6 2. Nf3 d5 3. Nc3 Nf6 4. e5 Ne4 5. Ne2 Bf5 6. Nfd4 e6 7. Nxf5 exf5 8. c3 Nd7 9. d4 Be7 10. Qb3 O-O 11. f3 Ng5 12. Qxb7 Rc8 13. Nf4 Ne6 14. Be2 a5 15. Qb3 g5 16. Nxe6
*'
# the $' ' shell quoting allows longform pgn with newlines, including headers, to be quoted into a single shell arg

python queue_pgn.py TCEC_Season_24_-_Division_P.pgn
```


##### Purpose

The purpose and priorities of this little project are, in order:

###### 1) To be usable, readable and maintainable.

These aren't all *exactly* the same, but they're of course intimately related.

It is my present belief that use of the Python keywords `async` and `await` are the best route to this goal, and the use
of threads for doing HTTP requests is bad practice -- but I'm open to being proven wrong.

In particular, I was swayed by NJS's blogposts that furthermore, one should be using `async` and `await` in a *structured*
way, hence the use of `trio` for the library and scripts (the API is agnostic).

The big link: https://vorpus.org/blog/notes-on-structured-concurrency-or-go-statement-considered-harmful/

other related ones:
https://vorpus.org/blog/some-thoughts-on-asynchronous-api-design-in-a-post-asyncawait-world/
https://vorpus.org/blog/control-c-handling-in-python-and-trio/
> The tl;dr is: if you're writing a program using trio, then control-C should generally Just Work the way you expect from
> regular Python, i.e., it will raise KeyboardInterrupt somewhere in your code, and this exception then propagates out
> to unwind your stack, run cleanup handlers, and eventually exit the program.
https://vorpus.org/blog/timeouts-and-cancellation-for-humans/

As per that quote, one of the many advantages of structured concurrency is that ^C should generally "just work" in this
package without me having done anything special to achieve that, thanks to trio's efforts under the hood.


###### 2) To be fast, in terms of requests per second.

I believe `async`/`await` is again the best way to achieve this goal, rather than with threads or other stuff. At present,
this package is capable of around 400-500 requests/second, depending on your CPU, and there remains lots of room for more
(although there is no rush for more since that's already enough to challenge CDB's backend elves).
