import logging
import os
import secrets
from logging.handlers import WatchedFileHandler

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        SQLALCHEMY_DATABASE_URI="sqlite:///jobcheck.db",  # relative to instance/
        MAX_CONTENT_LENGTH=5 * 1024 * 1024,
    )
    app.config.update(config or {})
    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    from app import models, routes  # models must load before create_all
    app.register_blueprint(routes.bp)
    with app.app_context():
        db.create_all()

    if not app.testing:
        setup_logging(app)
    return app


def setup_logging(app):
    log_dir = os.path.join(os.path.dirname(app.root_path), "logs")
    os.makedirs(log_dir, exist_ok=True)
    # WatchedFileHandler reopens the file after scripts/ rotate it by renaming
    handler = WatchedFileHandler(os.path.join(log_dir, "app.log"))
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)
