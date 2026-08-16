import sqlite3

import click
from flask import current_app, g


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
    display_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_synced_at TEXT,
    blitz_rating INTEGER,
    blitz_rating_date TEXT,
    rapid_rating INTEGER,
    rapid_rating_date TEXT
);

CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT NOT NULL UNIQUE,
    url TEXT,
    pgn TEXT NOT NULL,
    played_at INTEGER NOT NULL,
    played_date TEXT NOT NULL,
    time_class TEXT,
    time_control TEXT,
    rated INTEGER NOT NULL DEFAULT 0,
    white_username TEXT NOT NULL,
    black_username TEXT NOT NULL,
    white_rating INTEGER,
    black_rating INTEGER,
    result TEXT NOT NULL,
    termination TEXT,
    eco TEXT,
    opening_name TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_games_played_date ON games(played_date);
CREATE INDEX IF NOT EXISTS idx_games_time_class ON games(time_class);

CREATE TABLE IF NOT EXISTS account_games (
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    color TEXT NOT NULL CHECK (color IN ('white', 'black')),
    outcome TEXT NOT NULL CHECK (outcome IN ('win', 'draw', 'loss')),
    PRIMARY KEY (account_id, game_id)
);

CREATE INDEX IF NOT EXISTS idx_account_games_game ON account_games(game_id);

CREATE TABLE IF NOT EXISTS game_moves (
    game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    ply INTEGER NOT NULL,
    position_key TEXT NOT NULL,
    san TEXT NOT NULL,
    uci TEXT NOT NULL,
    PRIMARY KEY (game_id, ply)
);

CREATE INDEX IF NOT EXISTS idx_game_moves_position ON game_moves(position_key);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript(SCHEMA)
    existing = {row["name"] for row in db.execute("PRAGMA table_info(accounts)").fetchall()}
    for name, sql_type in {
        "blitz_rating": "INTEGER",
        "blitz_rating_date": "TEXT",
        "rapid_rating": "INTEGER",
        "rapid_rating_date": "TEXT",
    }.items():
        if name not in existing:
            db.execute(f"ALTER TABLE accounts ADD COLUMN {name} {sql_type}")
    db.commit()


@click.command("init-db")
def init_db_command():
    init_db()
    click.echo("Initialized the database.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    with app.app_context():
        init_db()
