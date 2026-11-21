"""Application configuration.

All secrets come from environment variables. Nothing sensitive is hard-coded.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        instance = BASE_DIR / "instance"
        instance.mkdir(exist_ok=True)
        return f"sqlite:///{instance / 'sleep360.db'}"
    # Render/Heroku hand out postgres:// URLs; SQLAlchemy 2 wants postgresql+psycopg://
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://") :]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "")
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # Sessions / cookies
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "1") == "1"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * 14  # 14 days

    # CSRF: JSON API calls send the token in the X-CSRFToken header
    WTF_CSRF_TIME_LIMIT = None

    # Rate limiting (in-memory by default; set RATELIMIT_STORAGE_URI=redis://... in prod)
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_HEADERS_ENABLED = True

    # AI assistant
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-5-5")
    ASSISTANT_MAX_TOKENS = int(os.environ.get("ASSISTANT_MAX_TOKENS", "700"))

    # Uploads (CSV import)
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024  # 2 MB

    MODEL_PATH = Path(os.environ.get("MODEL_PATH", BASE_DIR / "sleep360" / "ml" / "artifacts" / "fatigue_model.joblib"))


class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-only-insecure-key"


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = "test-key"  # noqa: S105 (tests only)
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    ANTHROPIC_API_KEY = ""


class ProductionConfig(Config):
    DEBUG = False


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
