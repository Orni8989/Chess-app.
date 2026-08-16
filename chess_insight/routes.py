import chess
import chess.svg
from flask import Blueprint, Response, jsonify, render_template, request

from .analysis import account_list, decision_points, next_moves, overview
from .chesscom import ChessComError
from .sync import sync_account

bp = Blueprint("main", __name__)


def _integer_list(value):
    result = []
    for item in value.split(",") if value else []:
        try:
            result.append(int(item))
        except ValueError:
            continue
    return result


def _filters():
    classes = [item for item in request.args.get("time_classes", "").split(",") if item]
    return {
        "account_ids": _integer_list(request.args.get("accounts", "")),
        "start": request.args.get("start") or None,
        "end": request.args.get("end") or None,
        "time_classes": classes,
    }


@bp.get("/")
def explorer_page():
    return render_template("explorer.html", page="explorer")


@bp.get("/insights")
def insights_page():
    return render_template("insights.html", page="insights")


@bp.get("/api/accounts")
def accounts_api():
    return jsonify({"accounts": account_list()})


@bp.get("/pieces/<piece_code>.svg")
def piece_svg(piece_code):
    if len(piece_code) != 2 or piece_code[0] not in {"w", "b"} or piece_code[1] not in "KQRBNP":
        return Response(status=404)
    symbol = piece_code[1] if piece_code[0] == "w" else piece_code[1].lower()
    svg = chess.svg.piece(chess.Piece.from_symbol(symbol), size=96)
    return Response(svg, mimetype="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})


@bp.post("/api/accounts/sync")
def sync_api():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username", "")).strip()
    if not username or len(username) > 50:
        return jsonify({"error": "Enter a valid Chess.com username."}), 400
    try:
        result = sync_account(username, payload.get("start") or None, payload.get("end") or None)
    except (ChessComError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify(result)


@bp.get("/api/overview")
def overview_api():
    return jsonify(overview(**_filters()))


@bp.get("/api/explorer")
def explorer_api():
    filters = _filters()
    path = [item for item in request.args.get("path", "").split("|") if item]
    color = request.args.get("color", "white")
    if color not in {"white", "black"}:
        color = "white"
    try:
        limit = min(20, max(1, int(request.args.get("limit", 5))))
    except ValueError:
        limit = 5
    return jsonify(next_moves(path, color=color, limit=limit, **filters))


@bp.get("/api/insights")
def insights_api():
    filters = _filters()
    try:
        depth = min(40, max(2, int(request.args.get("depth", 12))))
        minimum = min(500, max(1, int(request.args.get("minimum", 15))))
    except ValueError:
        return jsonify({"error": "Depth and minimum games must be numbers."}), 400
    return jsonify({"insights": decision_points(depth=depth, minimum=minimum, **filters)})
