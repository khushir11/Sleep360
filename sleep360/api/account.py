from __future__ import annotations

import json
from datetime import date, timedelta

from flask import Response, request, session
from flask_login import current_user, login_required, logout_user

from ..extensions import db
from ..schemas import DeleteAccountIn, PasswordChangeIn, SettingsIn
from ..services import assessments, queries
from ..services.reports import export_all, weekly_pdf
from . import APIError, bp, parse


@bp.get("/account")
@login_required
def get_account():
    return {"user": current_user.to_dict()}


@bp.patch("/account")
@login_required
def update_account():
    data = parse(SettingsIn).model_dump(exclude_unset=True)
    score_inputs_changed = any(k in data for k in ("sleep_goal_hours", "target_wake_time"))
    for k, v in data.items():
        setattr(current_user, k, v)
    db.session.commit()
    if score_inputs_changed:  # goals feed the sleep score; recompute recent history
        today = queries.user_today(current_user)
        assessments.reassess_range(current_user, today - timedelta(days=30), today)
    return {"user": current_user.to_dict()}


@bp.post("/account/password")
@login_required
def change_password():
    if current_user.is_demo:
        raise APIError(403, "demo_account", "Demo accounts can't set a password. Create a free account instead.")
    data = parse(PasswordChangeIn)
    if not current_user.check_password(data.current_password):
        raise APIError(400, "invalid_password", "Current password is incorrect")
    current_user.set_password(data.new_password)
    db.session.commit()
    return {"ok": True}


@bp.get("/account/export")
@login_required
def export():
    body = json.dumps(export_all(current_user), indent=2, default=str)
    return Response(
        body,
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename=sleep360-export-{date.today()}.json"},
    )


@bp.delete("/account")
@login_required
def delete_account():
    if not current_user.is_demo:
        data = parse(DeleteAccountIn)
        if not current_user.check_password(data.password):
            raise APIError(400, "invalid_password", "Password is incorrect")
    user = db.session.get(type(current_user._get_current_object()), current_user.id)
    logout_user()
    session.clear()
    db.session.delete(user)  # cascades to every user-owned table
    db.session.commit()
    return "", 204


@bp.get("/reports/weekly.pdf")
@login_required
def weekly_report():
    end = None
    if request.args.get("end"):
        try:
            end = date.fromisoformat(request.args["end"])
        except ValueError:
            raise APIError(400, "bad_request", "'end' must be YYYY-MM-DD")
    pdf = weekly_pdf(current_user, end)
    fname = f"sleep360-week-{(end or queries.user_today(current_user)).isoformat()}.pdf"
    return Response(pdf, mimetype="application/pdf", headers={"Content-Disposition": f"attachment; filename={fname}"})
