from chess_insight.analysis import decision_points, next_moves, overview
from chess_insight.ingest import store_game, upsert_account


def payload(game_id, moves, result="1-0", white="Tester", black="Opponent", end_time=1704067200):
    pgn_moves = " ".join(moves)
    pgn = f'''[Event "Live Chess"]
[Site "Chess.com"]
[Date "2024.01.01"]
[White "{white}"]
[Black "{black}"]
[Result "{result}"]
[ECO "C20"]
[Opening "King's Pawn Game"]

{pgn_moves} {result}
'''
    return {
        "url": f"https://www.chess.com/game/live/{game_id}", "pgn": pgn,
        "end_time": end_time, "time_class": "blitz", "time_control": "300",
        "rated": True, "white": {"username": white, "rating": 2000},
        "black": {"username": black, "rating": 1980},
    }


def seed_games(app):
    with app.app_context():
        account = upsert_account("Tester")
        store_game(account["id"], "Tester", payload("1", ["1.", "e4", "e5", "2.", "Nf3", "Nc6"], "1-0"))
        store_game(account["id"], "Tester", payload("2", ["1.", "e4", "c5", "2.", "Nf3", "d6"], "1/2-1/2", end_time=1704153600))
        store_game(account["id"], "Tester", payload("3", ["1.", "d4", "d5", "2.", "c4", "e6"], "0-1", end_time=1704240000))
        from chess_insight.db import get_db
        get_db().commit()
        return account["id"]


def test_opening_explorer_groups_moves(app):
    account_id = seed_games(app)
    with app.app_context():
        root = next_moves([], account_ids=[account_id], color="white")
        assert root["actor"] == "you"
        assert root["fen"].startswith("rnbqkbnr/pppppppp")
        assert root["moves"][0]["san"] == "e4"
        assert root["moves"][0]["games"] == 2
        reply = next_moves(["e4"], account_ids=[account_id], color="white")
        assert reply["actor"] == "opponent"
        assert reply["fen"].startswith("rnbqkbnr/pppppppp/8/8/4P3")
        assert {move["san"] for move in reply["moves"]} == {"e5", "c5"}


def test_overview_and_decision_points(app):
    account_id = seed_games(app)
    with app.app_context():
        summary = overview(account_ids=[account_id])
        assert summary["games"] == 3
        assert summary["expected_score"] == 0.5
        insights = decision_points(account_ids=[account_id], depth=4, minimum=1)
        assert insights[0]["path"] == []
        assert insights[0]["spread"] == 0.75


def test_pages_and_empty_api(client):
    page = client.get("/")
    assert page.status_code == 200
    assert b'type="button" class="dialog-close"' in page.data
    assert b'id="hide-sidebar"' in page.data
    assert client.get("/insights").status_code == 200
    assert client.get("/api/explorer").get_json()["moves"] == []
    piece = client.get("/pieces/wK.svg")
    assert piece.status_code == 200
    assert piece.content_type.startswith("image/svg+xml")


def test_zero_account_filter_excludes_every_game(app, client):
    seed_games(app)
    assert client.get("/api/overview?accounts=0").get_json()["games"] == 0
    assert client.get("/api/explorer?accounts=0").get_json()["moves"] == []


def test_account_api_includes_rating_fields(app, client):
    seed_games(app)
    account = client.get("/api/accounts").get_json()["accounts"][0]
    assert "blitz_rating" in account
    assert "rapid_rating" in account
