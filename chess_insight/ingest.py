import hashlib
import io
import re
from datetime import datetime, timezone

import chess.pgn

from .db import get_db


def normalized_position_key(board):
    parts = board.fen().split()
    return " ".join(parts[:4])


def _outcome(result, color):
    if result == "1/2-1/2":
        return "draw"
    if (result == "1-0" and color == "white") or (result == "0-1" and color == "black"):
        return "win"
    return "loss"


def _external_id(payload):
    url = payload.get("url")
    if url:
        return url.rstrip("/").split("/")[-1]
    fingerprint = f"{payload.get('end_time')}|{payload.get('pgn', '')}"
    return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()


def _header_rating(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_game(payload):
    pgn_text = payload.get("pgn", "")
    parsed = chess.pgn.read_game(io.StringIO(pgn_text))
    if parsed is None:
        raise ValueError("Game has no readable PGN.")

    headers = parsed.headers
    white = payload.get("white", {})
    black = payload.get("black", {})
    played_at = int(payload.get("end_time") or 0)
    if not played_at:
        date_text = headers.get("UTCDate") or headers.get("Date")
        time_text = headers.get("UTCTime", "00:00:00")
        played_at = int(datetime.strptime(f"{date_text} {time_text}", "%Y.%m.%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp())

    moves = []
    board = parsed.board()
    for ply, move in enumerate(parsed.mainline_moves()):
        moves.append(
            {
                "ply": ply,
                "position_key": normalized_position_key(board),
                "san": board.san(move),
                "uci": move.uci(),
            }
        )
        board.push(move)

    opening_name = headers.get("Opening") or headers.get("ECOUrl", "").rstrip("/").split("/")[-1].replace("-", " ") or None
    return {
        "external_id": _external_id(payload),
        "url": payload.get("url"),
        "pgn": pgn_text,
        "played_at": played_at,
        "played_date": datetime.fromtimestamp(played_at, tz=timezone.utc).date().isoformat(),
        "time_class": payload.get("time_class"),
        "time_control": payload.get("time_control"),
        "rated": int(bool(payload.get("rated"))),
        "white_username": white.get("username") or headers.get("White", "Unknown"),
        "black_username": black.get("username") or headers.get("Black", "Unknown"),
        "white_rating": _header_rating(white.get("rating") or headers.get("WhiteElo")),
        "black_rating": _header_rating(black.get("rating") or headers.get("BlackElo")),
        "result": headers.get("Result", "*"),
        "termination": headers.get("Termination"),
        "eco": headers.get("ECO"),
        "opening_name": opening_name,
        "moves": moves,
    }


def upsert_account(username):
    db = get_db()
    clean = username.strip()
    db.execute(
        "INSERT INTO accounts (username, display_name) VALUES (?, ?) ON CONFLICT(username) DO UPDATE SET display_name = excluded.display_name",
        (clean.lower(), clean),
    )
    db.commit()
    return db.execute("SELECT * FROM accounts WHERE username = ?", (clean.lower(),)).fetchone()


def store_game(account_id, username, payload):
    data = parse_game(payload)
    db = get_db()
    db.execute(
        """
        INSERT INTO games (
            external_id, url, pgn, played_at, played_date, time_class, time_control,
            rated, white_username, black_username, white_rating, black_rating,
            result, termination, eco, opening_name
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(external_id) DO NOTHING
        """,
        (
            data["external_id"], data["url"], data["pgn"], data["played_at"],
            data["played_date"], data["time_class"], data["time_control"],
            data["rated"], data["white_username"], data["black_username"],
            data["white_rating"], data["black_rating"], data["result"],
            data["termination"], data["eco"], data["opening_name"],
        ),
    )
    game = db.execute("SELECT id FROM games WHERE external_id = ?", (data["external_id"],)).fetchone()
    existing_moves = db.execute("SELECT 1 FROM game_moves WHERE game_id = ? LIMIT 1", (game["id"],)).fetchone()
    if not existing_moves:
        db.executemany(
            "INSERT INTO game_moves (game_id, ply, position_key, san, uci) VALUES (?, ?, ?, ?, ?)",
            [(game["id"], move["ply"], move["position_key"], move["san"], move["uci"]) for move in data["moves"]],
        )

    color = "white" if data["white_username"].casefold() == username.casefold() else "black"
    db.execute(
        "INSERT OR IGNORE INTO account_games (account_id, game_id, color, outcome) VALUES (?, ?, ?, ?)",
        (account_id, game["id"], color, _outcome(data["result"], color)),
    )
    return db.total_changes


def month_bounds(value):
    if not value or not re.fullmatch(r"\d{4}-\d{2}", value):
        return None
    return value
