from pathlib import Path

from flask import Flask


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY="dev",
        DATABASE=str(Path(app.instance_path) / "chess_insight.sqlite3"),
        CHESSCOM_USER_AGENT="ChessInsight/0.1 (local personal analysis tool)",
        SYNC_REQUEST_DELAY=0.12,
    )

    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    from . import db
    db.init_app(app)

    from .routes import bp
    app.register_blueprint(bp)

    return app
