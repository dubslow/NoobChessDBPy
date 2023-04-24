A currently-skeletal python interface to CDB using async+trio.

See `scripts/` for basic usage examples, together with `help()` on the imports
demonstrated therein.

No promises of utility. Feedback welcome, via this repo or Stockfish Discord.

Can be used in the ~standard python way:

```
mkdir noobchessdbpy
cd noobchessdbpy

git clone <this> .

# make and use virtualenv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# now try some example scripts
cd scripts
python queue_single_line.py $'1. e4 c6 2. Nf3 d5 3. Nc3 Nf6 4. e5 Ne4 5. Ne2 Bf5 6. Nfd4 e6 7. Nxf5 exf5 8. c3 Nd7 9. d4 Be7 10. Qb3 O-O 11. f3 Ng5 12. Qxb7 Rc8 13. Nf4 Ne6 14. Be2 a5 15. Qb3 g5 16. Nxe6
*'
# that starts analysis of every position in that line. the $' ' shell quoting allows
# longform pgn to be quoted into a single shell arg
```
