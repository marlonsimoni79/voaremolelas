"""Application entry point for the voaremolelas web app."""

from __future__ import annotations

import logging

from flask import Flask

from app.api.routes import api
from app.config import config


def create_app() -> Flask:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.register_blueprint(api)
    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5555)
