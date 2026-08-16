import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from flask import current_app


class ChessComError(RuntimeError):
    pass


def _get_json(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": current_app.config["CHESSCOM_USER_AGENT"],
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise ChessComError("Chess.com user or archive not found.") from exc
        if exc.code == 429:
            raise ChessComError("Chess.com is rate-limiting requests. Try again shortly.") from exc
        raise ChessComError(f"Chess.com returned HTTP {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ChessComError("Could not reach Chess.com. Check your connection and retry.") from exc


def fetch_archive_urls(username):
    safe_username = urllib.parse.quote(username.strip())
    payload = _get_json(f"https://api.chess.com/pub/player/{safe_username}/games/archives")
    return payload.get("archives", [])


def fetch_archive(url):
    return _get_json(url).get("games", [])


def fetch_player_stats(username):
    safe_username = urllib.parse.quote(username.strip())
    return _get_json(f"https://api.chess.com/pub/player/{safe_username}/stats")


def archive_month(url):
    parts = url.rstrip("/").split("/")
    try:
        return f"{int(parts[-2]):04d}-{int(parts[-1]):02d}"
    except (ValueError, IndexError) as exc:
        raise ChessComError("Chess.com returned an invalid archive URL.") from exc


def select_archives(urls, from_date=None, to_date=None, latest_timestamp=None):
    earliest_month = from_date[:7] if from_date else None
    latest_month = to_date[:7] if to_date else None
    if latest_timestamp and not earliest_month:
        earliest_month = datetime.fromtimestamp(latest_timestamp, tz=timezone.utc).strftime("%Y-%m")

    selected = []
    for url in urls:
        month = archive_month(url)
        if earliest_month and month < earliest_month:
            continue
        if latest_month and month > latest_month:
            continue
        selected.append(url)
    return selected


def polite_pause():
    delay = float(current_app.config.get("SYNC_REQUEST_DELAY", 0))
    if delay:
        time.sleep(delay)
