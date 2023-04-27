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
This module adds some extra methods/algorithms to some `chess` classes for use in this package
'''

import chess
import chess.pgn
from typing import Iterable

########################################################################################################################

# Manually extend chess.Board with a utility algorithm:
def legal_child_boards(self, stack=True) -> chess.Board:
    '''A generator over the `legal_moves` of `self`, yielding *copies* of the
    resulting boards. `stack` is the same as for `self.copy`.'''
    for move in self.legal_moves:
        new = self.copy(stack=stack)
        new.push(move)
        yield new
chess.Board.legal_child_boards = legal_child_boards

########################################################################################################################
# Manually add some more methods to chess.pgn.GameNode

def pgn_parse_comment_pv_san(self) -> Iterable[str]:
    """
    Parse this node's comment for comma-separated key=value fields for the 'pv' field which is a list of SAN moves
    """
    for f in node.comment.split(','):
        f = f.strip()
        if f.startswith('pv'):
            pvfield = f
            break
    pvstr = pvfield.split('=')[1]
    return pvstr.split()

def add_line_by_san(self, sans: Iterable[str], *, comment: str = "", starting_comment: str = "", nags: Iterable[int] = []) -> chess.pgn.GameNode:
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

def custom_add_line_san(self, sans:Iterable[str]):
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

def all_variations(self):
    """
    An depth-first iterable yield `ChildNode`s from all variations starting from this node.
    """
    # could accept a visitor arg etc etc
    for vari in self.variations:
        yield vari
        yield from vari.all_variations()

chess.pgn.GameNode.pgn_parse_comment_pv_san = pgn_parse_comment_pv_san
chess.pgn.GameNode.custom_add_line_san      = custom_add_line_san
chess.pgn.GameNode.all_variations           = all_variations
