"""Chess engine tool using Stockfish"""

from typing import Dict, Any, Optional
from stockfish import Stockfish
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.box import DOUBLE
from strands import tool

console = Console()

# Global state
_stockfish_instance = None
_current_fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

PIECE_MAP = {
    "R": "♖",
    "N": "♘",
    "B": "♗",
    "Q": "♕",
    "K": "♔",
    "P": "♙",
    "r": "♜",
    "n": "♞",
    "b": "♝",
    "q": "♛",
    "k": "♚",
    "p": "♟",
}


def create_rich_board(board_str: str) -> Table:
    """Create rich board visualization"""
    table = Table(show_header=False, box=DOUBLE, padding=0, title="Chess Board")
    table.add_column("Row", style="bold cyan", width=2)
    for col in "abcdefgh":
        table.add_column(col, justify="center", width=3)

    rows = [
        r.strip() for r in board_str.split("\n") if r.strip() and not r.startswith("+")
    ]

    for i, row in enumerate(rows):
        row_num = 8 - i
        pieces = row.split("|")[1:9]
        styled_pieces = []
        for piece in pieces:
            piece = piece.strip()
            if piece and piece != " ":
                unicode_piece = PIECE_MAP.get(piece, piece)
                color = "white" if piece.isupper() else "red"
                styled_pieces.append(f"[{color}]{unicode_piece}[/]")
            else:
                styled_pieces.append("·")
        table.add_row(str(row_num), *styled_pieces)

    table.add_row("", *list("abcdefgh"), style="bold cyan")
    return table


@tool
def chess(
    action: str,
    fen: Optional[str] = None,
    move: Optional[str] = None,
    skill_level: int = 20,
    depth: int = 10,
) -> Dict[str, Any]:
    """Play chess and analyze positions using Stockfish

    Args:
        action: Action (get_best_move, make_move, evaluate_position, set_position, get_board_visual)
        fen: Optional FEN string for position
        move: Move in UCI format (e.g., 'e2e4')
        skill_level: Stockfish skill (0-20)
        depth: Search depth (1-20)

    Returns:
        Dict with status and content
    """
    global _stockfish_instance, _current_fen

    try:
        # Initialize Stockfish
        if _stockfish_instance is None:
            _stockfish_instance = Stockfish(path="/opt/homebrew/bin/stockfish")
            _stockfish_instance.set_position(_current_fen)

        _stockfish_instance.set_skill_level(skill_level)
        _stockfish_instance.set_depth(depth)

        # Set FEN if provided
        if fen:
            if not _stockfish_instance.is_fen_valid(fen):
                return {"status": "error", "content": [{"text": "❌ Invalid FEN"}]}
            _stockfish_instance.set_fen_position(fen)
            _current_fen = fen

        # Show board
        board_table = create_rich_board(_stockfish_instance.get_board_visual())
        console.print(Panel(board_table, title="Current Position"))

        result_text = []

        if action == "get_best_move":
            best_move = _stockfish_instance.get_best_move()
            result_text.append(f"✅ Best move: {best_move}")
            console.print(f"[cyan]Best move:[/] [green]{best_move}[/]")

        elif action == "make_move":
            if not move:
                return {"status": "error", "content": [{"text": "❌ Move required"}]}
            if not _stockfish_instance.is_move_correct(move):
                return {
                    "status": "error",
                    "content": [{"text": f"❌ Invalid move: {move}"}],
                }

            _stockfish_instance.make_moves_from_current_position([move])
            _current_fen = _stockfish_instance.get_fen_position()
            result_text.append(f"✅ Move made: {move}")
            result_text.append(f"FEN: {_current_fen}")

        elif action == "evaluate_position":
            eval_result = _stockfish_instance.get_evaluation()
            if eval_result["type"] == "cp":
                score = eval_result["value"] / 100
                result_text.append(f"✅ Evaluation: {score:+.2f} pawns")
            else:
                moves = eval_result["value"]
                result_text.append(f"✅ Mate in {abs(moves)} moves")

        elif action == "set_position":
            if not fen:
                return {"status": "error", "content": [{"text": "❌ FEN required"}]}
            _current_fen = fen
            result_text.append(f"✅ Position set")

        return {"status": "success", "content": [{"text": "\n".join(result_text)}]}

    except Exception as e:
        return {"status": "error", "content": [{"text": f"❌ Error: {str(e)}"}]}
