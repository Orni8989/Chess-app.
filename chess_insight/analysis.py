from collections import defaultdict

import chess

from .db import get_db


def _score(outcome):
    return {"win": 1.0, "draw": 0.5, "loss": 0.0}[outcome]


def _stats(outcomes):
    total = len(outcomes)
    wins = outcomes.count("win")
    draws = outcomes.count("draw")
    losses = outcomes.count("loss")
    if not total:
        return {"games": 0, "wins": 0, "draws": 0, "losses": 0, "win_pct": 0, "draw_pct": 0, "loss_pct": 0, "expected_score": 0}
    return {
        "games": total,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "win_pct": round(wins * 100 / total, 1),
        "draw_pct": round(draws * 100 / total, 1),
        "loss_pct": round(losses * 100 / total, 1),
        "expected_score": round(sum(_score(item) for item in outcomes) / total, 3),
    }


def _filters(account_ids=None, start=None, end=None, time_classes=None, color=None):
    where = []
    values = []
    if account_ids:
        placeholders = ",".join("?" for _ in account_ids)
        where.append(f"ag.account_id IN ({placeholders})")
        values.extend(account_ids)
    if start:
        where.append("g.played_date >= ?")
        values.append(start)
    if end:
        where.append("g.played_date <= ?")
        values.append(end)
    if time_classes:
        placeholders = ",".join("?" for _ in time_classes)
        where.append(f"g.time_class IN ({placeholders})")
        values.extend(time_classes)
    if color in {"white", "black"}:
        where.append("ag.color = ?")
        values.append(color)
    return (" AND " + " AND ".join(where)) if where else "", values


def load_sequences(account_ids=None, start=None, end=None, time_classes=None, color=None, max_plies=None):
    db = get_db()
    where_sql, values = _filters(account_ids, start, end, time_classes, color)
    rows = db.execute(
        f"""
        SELECT g.id, g.played_date, g.time_class, g.opening_name, g.eco,
               ag.account_id, ag.color, ag.outcome
        FROM account_games ag
        JOIN games g ON g.id = ag.game_id
        WHERE g.pgn NOT LIKE '%[SetUp "1"]%' {where_sql}
        ORDER BY g.played_at DESC
        """,
        values,
    ).fetchall()
    if not rows:
        return []

    game_ids = sorted({row["id"] for row in rows})
    placeholders = ",".join("?" for _ in game_ids)
    ply_limit = " AND ply < ?" if max_plies is not None else ""
    move_values = [*game_ids, max_plies] if max_plies is not None else game_ids
    move_rows = db.execute(
        f"SELECT game_id, ply, san, uci, position_key FROM game_moves WHERE game_id IN ({placeholders}){ply_limit} ORDER BY game_id, ply",
        move_values,
    ).fetchall()
    by_game = defaultdict(list)
    for move in move_rows:
        by_game[move["game_id"]].append(dict(move))

    return [{**dict(row), "moves": by_game[row["id"]]} for row in rows]


def overview(account_ids=None, start=None, end=None, time_classes=None):
    sequences = load_sequences(account_ids, start, end, time_classes)
    outcomes = [item["outcome"] for item in sequences]
    dates = [item["played_date"] for item in sequences]
    stats = _stats(outcomes)
    stats.update({"first_game": min(dates) if dates else None, "last_game": max(dates) if dates else None})
    return stats


def next_moves(path, account_ids=None, start=None, end=None, time_classes=None, color="white", limit=5):
    sequences = load_sequences(account_ids, start, end, time_classes, color=color, max_plies=len(path) + 1)
    groups = defaultdict(list)
    matched = []
    for game in sequences:
        sans = [move["san"] for move in game["moves"]]
        if sans[: len(path)] != path or len(sans) <= len(path):
            continue
        matched.append(game["outcome"])
        groups[sans[len(path)]].append(game["outcome"])

    user_is_white = color == "white"
    white_to_move = len(path) % 2 == 0
    actor = "you" if user_is_white == white_to_move else "opponent"
    moves = [
        {"san": san, **_stats(outcomes)}
        for san, outcomes in groups.items()
    ]
    moves.sort(key=lambda item: (-item["games"], -item["expected_score"], item["san"]))
    board = chess.Board()
    last_move = None
    valid_path = True
    for san in path:
        try:
            move = board.parse_san(san)
            last_move = move.uci()
            board.push(move)
        except (chess.IllegalMoveError, chess.InvalidMoveError, chess.AmbiguousMoveError):
            valid_path = False
            break

    return {
        "path": path,
        "actor": actor,
        "fen": board.fen(),
        "last_move": last_move,
        "valid_position": valid_path,
        "turn": "white" if board.turn == chess.WHITE else "black",
        "position": _stats(matched),
        "moves": moves[:limit],
        "other_move_count": max(0, len(moves) - limit),
    }


def decision_points(account_ids=None, start=None, end=None, time_classes=None, depth=12, minimum=15, limit=20):
    sequences = load_sequences(account_ids, start, end, time_classes, max_plies=depth)
    positions = defaultdict(lambda: defaultdict(list))

    for game in sequences:
        user_turn_parity = 0 if game["color"] == "white" else 1
        path = []
        for move in game["moves"]:
            if move["ply"] % 2 == user_turn_parity:
                positions[tuple(path)][move["san"]].append(game["outcome"])
            path.append(move["san"])

    insights = []
    for path, candidates in positions.items():
        qualifying = [
            {"san": san, **_stats(outcomes)}
            for san, outcomes in candidates.items()
            if len(outcomes) >= minimum
        ]
        if len(qualifying) < 2:
            continue
        qualifying.sort(key=lambda item: (-item["expected_score"], -item["games"]))
        spread = qualifying[0]["expected_score"] - qualifying[-1]["expected_score"]
        insights.append(
            {
                "path": list(path),
                "label": "Start position" if not path else " ".join(path),
                "ply": len(path),
                "games": sum(item["games"] for item in qualifying),
                "spread": round(spread, 3),
                "moves": qualifying,
            }
        )

    insights.sort(key=lambda item: (-item["spread"], -item["games"], item["ply"]))
    return insights[:limit]


def account_list():
    db = get_db()
    return [
        dict(row)
        for row in db.execute(
            """
            SELECT a.*, COUNT(ag.game_id) AS game_count,
                   MIN(g.played_date) AS first_game, MAX(g.played_date) AS last_game
            FROM accounts a
            LEFT JOIN account_games ag ON ag.account_id = a.id
            LEFT JOIN games g ON g.id = ag.game_id
            GROUP BY a.id
            ORDER BY a.display_name COLLATE NOCASE
            """
        ).fetchall()
    ]
