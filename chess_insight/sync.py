from datetime import datetime, timezone

from .chesscom import fetch_archive, fetch_archive_urls, fetch_player_stats, polite_pause, select_archives
from .db import get_db
from .ingest import store_game, upsert_account


def sync_account(username, from_date=None, to_date=None):
    account = upsert_account(username)
    db = get_db()
    latest = db.execute(
        "SELECT MAX(g.played_at) AS timestamp FROM games g JOIN account_games ag ON ag.game_id = g.id WHERE ag.account_id = ?",
        (account["id"],),
    ).fetchone()["timestamp"]

    urls = fetch_archive_urls(username)
    stats = fetch_player_stats(username)
    archives = select_archives(urls, from_date=from_date, to_date=to_date, latest_timestamp=latest)
    games_seen = 0
    linked_before = db.execute("SELECT COUNT(*) FROM account_games WHERE account_id = ?", (account["id"],)).fetchone()[0]

    for index, url in enumerate(archives):
        if index:
            polite_pause()
        for payload in fetch_archive(url):
            played_at = int(payload.get("end_time") or 0)
            played_date = datetime.fromtimestamp(played_at, tz=timezone.utc).date().isoformat() if played_at else ""
            if from_date and played_date < from_date:
                continue
            if to_date and played_date > to_date:
                continue
            store_game(account["id"], username, payload)
            games_seen += 1
        db.commit()

    def rating_details(key):
        last = stats.get(key, {}).get("last", {})
        timestamp = last.get("date")
        rating_date = datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat() if timestamp else None
        return last.get("rating"), rating_date

    blitz_rating, blitz_date = rating_details("chess_blitz")
    rapid_rating, rapid_date = rating_details("chess_rapid")
    db.execute(
        """
        UPDATE accounts
        SET last_synced_at = CURRENT_TIMESTAMP,
            blitz_rating = ?, blitz_rating_date = ?,
            rapid_rating = ?, rapid_rating_date = ?
        WHERE id = ?
        """,
        (blitz_rating, blitz_date, rapid_rating, rapid_date, account["id"]),
    )
    db.commit()
    linked_after = db.execute("SELECT COUNT(*) FROM account_games WHERE account_id = ?", (account["id"],)).fetchone()[0]
    return {
        "account": account["display_name"],
        "archives_checked": len(archives),
        "games_seen": games_seen,
        "games_added": linked_after - linked_before,
        "blitz_rating": blitz_rating,
        "rapid_rating": rapid_rating,
    }
