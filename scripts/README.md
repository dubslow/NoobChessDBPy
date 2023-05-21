## CDB interaction scripts

At the present time, the scripts are loosely separated into querying scripts vs queueing scripts, and additionally into
"read input from command line" (`paste`) or "read input from file" (`files`) scripts. There's also the fledgling
`near_pv*` family.

For querying there's a couple basic "paste FEN into command line" and "read FENs from file" skeleton examples, as well
as some slightly fancier breadth-first style mass-querying of a couple types. Some of the `near_pv*` family may be used
as essentially query/reading scripts.

For queuing, there's options for PGN input, uci output as input, or SAN input, be they from files or pasted into the
command line. I particularly recommend the use of `queue_paste_pgn.py` as a great way to enqueue live TCEC PVs into
CDB as games are played in real time. `queue_paste_fen_san.py` can also be used for similar purposes, e.g. to enqueue
Sesse's output concerning a live human game.

Many more uses of CDB beyond these are possible, if only the user can conceive of them :) happy scripting!
