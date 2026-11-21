from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest

from sleep360 import create_app
from sleep360.extensions import db as _db


@pytest.fixture()
def app():
    # No app context is held open during requests: Flask would otherwise reuse it, sharing ``g``
    # (and Flask-Login's cached user) between test clients.
    app = create_app("testing")
    yield app
    with app.app_context():
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def register(client, email="a@example.com", password="Passw0rd!", name="Asha"):
    return client.post("/api/v1/auth/register", json={"name": name, "email": email, "password": password})


@pytest.fixture()
def auth_client(client):
    assert register(client).status_code == 201
    return client


@pytest.fixture()
def other_client(app):
    c = app.test_client()
    assert register(c, email="b@example.com", name="Bilal").status_code == 201
    return c


def night(day_offset: int = 0, bed="23:30", wake="07:00", **extra) -> dict:
    """Payload for the night ending ``day_offset`` days ago (0 = this morning, user tz)."""
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo("Asia/Kolkata")).date() - timedelta(days=day_offset)
    bh, bm = map(int, bed.split(":"))
    wh, wm = map(int, wake.split(":"))
    wake_dt = datetime.combine(today, time(wh, wm))
    bed_dt = datetime.combine(today if bh < 12 else today - timedelta(days=1), time(bh, bm))
    return {"bedtime": bed_dt.isoformat(), "wake_time": wake_dt.isoformat(), "quality": extra.pop("quality", 7), **extra}
