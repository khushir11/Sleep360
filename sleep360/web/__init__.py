"""Server-rendered page shells. Each page loads its data from the REST API."""

from __future__ import annotations

from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user, login_required

bp = Blueprint("web", __name__)

APP_PAGES = {
    "dashboard": "Dashboard",
    "sleep": "Sleep",
    "attendance": "Attendance",
    "planner": "Planner",
    "insights": "Insights",
    "assistant": "Assistant",
    "settings": "Settings",
}


@bp.get("/")
def landing():
    if current_user.is_authenticated:
        return redirect(url_for("web.page", name="dashboard"))
    return render_template("pages/landing.html")


@bp.get("/login")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("web.page", name="dashboard"))
    return render_template("pages/auth.html", mode="login")


@bp.get("/register")
def register():
    if current_user.is_authenticated:
        return redirect(url_for("web.page", name="dashboard"))
    return render_template("pages/auth.html", mode="register")


@bp.get("/model")
def model():
    return render_template("pages/model.html", page="model", title="How the model works")


@bp.get("/privacy")
def privacy():
    return render_template("pages/privacy.html", page="privacy", title="Privacy")


@bp.get("/<any(dashboard, sleep, attendance, planner, insights, assistant, settings):name>")
@login_required
def page(name: str):
    return render_template(f"pages/{name}.html", page=name, title=APP_PAGES[name])
