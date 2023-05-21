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
This module adds some extra methods/algorithms to some `chess` classes for use in this package, exposing no symbols of
its own.
'''

########################################################################################################################

import chess
import chess.pgn
from typing import Iterable

__all__ = [] # this module only modifies other modules

########################################################################################################################
# Manually extend chess.Board with a couple utility algorithms

# TODO: apparently chess.Board.fen() is considerably expensive cpu-wise, altho the fenstr takes nearly 9x less memory...
def legal_child_fens(self, stack=True) -> Iterable:
    '''A generator over the `legal_moves` of `self`, yielding resulting fens.
    `stack` is the same as for `self.copy`.'''
    for move in self.legal_moves:
        new = self.copy(stack=stack)
        new.push(move)
        yield new.fen()

def yield_fens_from_sans(self, sans:Iterable) -> Iterable:
    """
    From the given board, parse a list of SAN moves into an iterable of FEN strings.
    """
    board = self.copy(stack=False)
    for san in sans:
        board.push_san(san)
        yield board.fen()

def safe_peek(self):
    try:
        return self.peek()
    except IndexError:
        return None

chess.Board.legal_child_fens   = legal_child_fens
chess.Board.yield_fens_from_sans = yield_fens_from_sans
chess.Board.safe_peek = safe_peek

########################################################################################################################
# Manually add some more methods to chess.pgn.GameNode

def parse_comment_pv_san(self):
    """
    Parse this node's comment for comma-separated key=value fields for the 'pv' field which is a list of SAN moves.
    In general we expect the PV to originate from this node's parent, and rarely may differ from this node's move.

    Uses `cur_board` to check if the first SAN duplicates the move leading to this node, and if so, excludes that first
    SAN.
    """
    for f in self.comment.split(','):
        f = f.strip()
        if f.startswith('pv'):
            pvfield = f
            break
    else:
        return None
    pvstr = pvfield.split('=', maxsplit=1)[1] # only split on first =, cause the rest are promotions lol
    sans = pvstr.split()
    return sans

def add_line_by_san(self, sans: Iterable, *, comment: str = "", starting_comment: str = "", nags: Iterable = []) -> chess.pgn.GameNode:
    """
    Creates a sequence of child nodes for the given list of SANs.
    Adds *comment* and *nags* to the last node of the line and returns it.

    Caution: repeated calls to GameNode.board() can be incredibly expensive, on the order of O(n^2)
    """
    node = self

    # Add line.
    for san in sans:
        node = node.add_variation(node.board().parse_san(san), starting_comment=starting_comment)
        starting_comment = ""

    # Merge comment and NAGs.
    if node.comment:
        node.comment += " " + comment
    else:
        node.comment = comment

    node.nags.update(nags)

    return node

def custom_add_line_san(self, sans:Iterable) -> chess.pgn.GameNode:
    """
    Creates a sequence of child nodes for the given list of SANs, using custom board control to avoid ChildNode.board()
    which is grossly expensive
    """
    node = self
    board = self.board()

    for san in sans:
        move = board.parse_san(san)
        board.push(move)
        node = node.add_variation(move)

    return node

def all_variations(self) -> Iterable:
    """
    An depth-first iterable yield `ChildNode`s from all variations starting from (and including) this node.
    """
    # could accept a visitor arg etc etc
    yield self
    for vari in self.variations:
        yield from vari.all_variations()

chess.pgn.GameNode.parse_comment_pv_san = parse_comment_pv_san
chess.pgn.GameNode.custom_add_line_san  = custom_add_line_san
chess.pgn.GameNode.all_variations       = all_variations
