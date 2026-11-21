from __future__ import annotations

from flask import session
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import select

from ..extensions import db, limiter
from ..models import User
from ..schemas import LoginIn, RegisterIn
from ..services.demo import create_demo_user
from . import APIError, bp, parse

# Constant-time-ish dummy hash so login timing doesn't reveal whether an email exists
_DUMMY = User(name="x", email="x", password_hash="")
_DUMMY.set_password("dummy-password-1")


@bp.post("/auth/register")
@limiter.limit("10 per hour")
def register():
    data = parse(RegisterIn)
    if db.session.scalar(select(User.id).where(User.email == data.email)):
        raise APIError(409, "email_taken", "An account with this email already exists")
    user = User(name=data.name, email=data.email)
    user.set_password(data.password)
    db.session.add(user)
    db.session.commit()
    session.clear()
    login_user(user)
    return {"user": user.to_dict()}, 201


@bp.post("/auth/login")
@limiter.limit("10 per minute; 50 per hour")
def login():
    data = parse(LoginIn)
    user = db.session.scalar(select(User).where(User.email == data.email))
    if user is None:
        _DUMMY.check_password(data.password)
        raise APIError(401, "invalid_credentials", "Incorrect email or password")
    if not user.check_password(data.password):
        raise APIError(401, "invalid_credentials", "Incorrect email or password")
    session.clear()  # prevent session fixation
    login_user(user, remember=data.remember)
    return {"user": user.to_dict()}


@bp.post("/auth/demo")
@limiter.limit("5 per hour")
def demo():
    user = create_demo_user()
    session.clear()
    login_user(user)
    return {"user": user.to_dict()}, 201


@bp.post("/auth/logout")
def logout():
    logout_user()
    session.clear()
    return {"ok": True}


@bp.get("/auth/me")
@login_required
def me():
    return {"user": current_user.to_dict()}
