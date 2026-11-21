"""REST API v1.

Conventions
-----------
* JSON in/out; errors are ``{"error": {"code", "message", "details?"}}``.
* Auth: Flask-Login session cookie. Mutating requests require the ``X-CSRFToken``
  header (Flask-WTF), which the frontend reads from a ``<meta>`` tag.
* All resources are scoped to ``current_user``; foreign ids return 404.
"""

from __future__ import annotations

from typing import TypeVar

from flask import Blueprint, jsonify, request
from flask_wtf.csrf import CSRFError
from pydantic import BaseModel, ValidationError
from werkzeug.exceptions import HTTPException

bp = Blueprint("api", __name__, url_prefix="/api/v1")

T = TypeVar("T", bound=BaseModel)


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str, details=None):
        self.status, self.code, self.message, self.details = status, code, message, details


def error(status: int, code: str, message: str, details=None):
    body = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return jsonify(body), status


def parse(schema: type[T]) -> T:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError(400, "bad_request", "Request body must be a JSON object")
    try:
        return schema.model_validate(data)
    except ValidationError as e:
        details = [
            {"field": ".".join(str(p) for p in err["loc"]) or None, "message": err["msg"].replace("Value error, ", "")}
            for err in e.errors()
        ]
        raise APIError(422, "validation_error", details[0]["message"] if details else "Invalid input", details)


@bp.errorhandler(APIError)
def _api_error(e: APIError):
    return error(e.status, e.code, e.message, e.details)


@bp.errorhandler(CSRFError)
def _csrf(e):
    return error(400, "csrf_failed", "Your session expired. Refresh the page and try again.")


@bp.errorhandler(HTTPException)
def _http(e: HTTPException):
    codes = {404: "not_found", 405: "method_not_allowed", 401: "unauthorized", 413: "too_large", 429: "rate_limited"}
    return error(e.code or 500, codes.get(e.code, "http_error"), e.description or e.name)


@bp.get("/health")
def health():
    from ..extensions import db

    db.session.execute(db.text("SELECT 1"))
    return {"status": "ok"}


# Route modules register themselves on ``bp``
from . import account, assistant, attendance, auth, insights, planner, sleep  # noqa: E402,F401
