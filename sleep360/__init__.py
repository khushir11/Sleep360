"""Sleep360 application factory."""

from __future__ import annotations

import logging
import os

from flask import Flask, jsonify, request

from .config import CONFIGS
from .extensions import csrf, db, limiter, login_manager, migrate

__version__ = "2.0.0"


def create_app(config_name: str | None = None) -> Flask:
    config_name = config_name or os.environ.get("FLASK_ENV_NAME") or os.environ.get("APP_ENV", "development")
    app = Flask(__name__)
    app.config.from_object(CONFIGS[config_name])

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY must be set (see .env.example)")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)  # batch mode so ALTERs work on SQLite too
    csrf.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "web.login"
    login_manager.session_protection = "strong"

    from . import models  # noqa: F401  (register models with SQLAlchemy metadata)

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(models.User, int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized():
        if request.path.startswith("/api/"):
            return jsonify({"error": {"code": "unauthorized", "message": "Please sign in"}}), 401
        from flask import redirect, url_for

        return redirect(url_for("web.login", next=request.path))

    from .api import bp as api_bp
    from .web import bp as web_bp

    app.register_blueprint(api_bp)
    app.register_blueprint(web_bp)

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
            "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
        )
        if request.path.startswith("/api/"):
            resp.headers.setdefault("Cache-Control", "no-store")
        if not app.debug and request.is_secure:
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return resp

    @app.errorhandler(429)
    def ratelimited(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": {"code": "rate_limited", "message": "Too many requests. Please wait a moment."}}), 429
        return "Too many requests", 429

    from .cli import register_cli

    register_cli(app)

    if app.config.get("TESTING"):
        with app.app_context():
            db.create_all()  # tests use an in-memory DB; every other environment runs `flask db upgrade`

    return app
