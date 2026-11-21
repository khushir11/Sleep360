from __future__ import annotations

from flask import current_app, request
from flask_login import current_user, login_required

from ..ml.predictor import get_predictor
from ..schemas import Strict
from ..services import assessments, dashboard, notifications
from ..services.achievements import evaluate as evaluate_achievements
from ..services.recommendations import generate
from . import APIError, bp, parse


@bp.get("/dashboard")
@login_required
def get_dashboard():
    notifications.scan(current_user)
    return dashboard.dashboard(current_user)


@bp.get("/analytics")
@login_required
def get_analytics():
    return dashboard.analytics(current_user, request.args.get("days", 30, type=int))


@bp.get("/recommendations")
@login_required
def get_recommendations():
    return {"items": generate(current_user)}


@bp.get("/assessment/latest")
@login_required
def latest_assessment():
    pair = assessments.latest_two(current_user)
    cur = pair[0] if pair else None
    prev = pair[1] if len(pair) > 1 else None
    return {"assessment": assessments.assessment_dict(cur), "change": assessments.explain_change(cur, prev)}


@bp.get("/achievements")
@login_required
def get_achievements():
    return evaluate_achievements(current_user)


@bp.get("/model")
def model_card():
    """Public model card: what the model is, how it was evaluated, and its limits."""
    p = get_predictor(current_app.config["MODEL_PATH"])
    if p is None:
        raise APIError(503, "model_unavailable", "The fatigue model is not loaded. Run `flask ml train`.")
    return p.card


@bp.get("/notifications")
@login_required
def list_notifications():
    items = notifications.unread(current_user)
    return {"items": [n.to_dict() for n in items], "unread": sum(1 for n in items if n.read_at is None)}


class MarkReadIn(Strict):
    ids: list[int] | None = None


@bp.post("/notifications/read")
@login_required
def read_notifications():
    data = parse(MarkReadIn)
    notifications.mark_read(current_user, data.ids)
    return {"ok": True}
