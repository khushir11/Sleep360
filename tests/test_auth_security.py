from sleep360 import create_app
from sleep360.models import User

from .conftest import night, register


def test_register_login_logout_flow(client):
    r = register(client)
    assert r.status_code == 201
    assert "password" not in str(r.json)
    assert client.get("/api/v1/auth/me").status_code == 200
    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/auth/me").status_code == 401
    r = client.post("/api/v1/auth/login", json={"email": "A@Example.com", "password": "Passw0rd!"})
    assert r.status_code == 200


def test_password_is_hashed(app, client):
    register(client)
    with app.app_context():
        u = User.query.filter_by(email="a@example.com").one()
    assert u.password_hash != "Passw0rd!"
    assert u.password_hash.startswith(("scrypt:", "pbkdf2:"))


def test_wrong_password_and_unknown_email_look_identical(client):
    register(client)
    client.post("/api/v1/auth/logout")
    a = client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "nope"})
    b = client.post("/api/v1/auth/login", json={"email": "ghost@example.com", "password": "nope"})
    assert a.status_code == b.status_code == 401
    assert a.json == b.json


def test_duplicate_email_and_weak_password(client):
    register(client)
    assert register(client).status_code == 409
    r = client.post("/api/v1/auth/register", json={"name": "x", "email": "c@example.com", "password": "short"})
    assert r.status_code == 422 and r.json["error"]["code"] == "validation_error"
    r = client.post("/api/v1/auth/register", json={"name": "x", "email": "c@example.com", "password": "allletters"})
    assert r.status_code == 422


def test_unknown_fields_rejected(client):
    r = client.post(
        "/api/v1/auth/register", json={"name": "x", "email": "c@example.com", "password": "Passw0rd!", "is_demo": True}
    )
    assert r.status_code == 422


def test_protected_endpoints_require_login(client):
    for path in ["/api/v1/dashboard", "/api/v1/sleep", "/api/v1/attendance", "/api/v1/tasks", "/api/v1/account/export"]:
        assert client.get(path).status_code == 401
    assert client.get("/dashboard").status_code == 302  # page redirects to login


def test_user_cannot_access_another_users_data(auth_client, other_client):
    log = auth_client.post("/api/v1/sleep", json=night(0)).json["log"]
    sem = auth_client.post("/api/v1/semesters", json={"name": "S1", "start_date": "2026-08-01", "end_date": "2026-12-20"}).json
    sub = auth_client.post("/api/v1/subjects", json={"semester_id": sem["id"], "name": "Maths"}).json
    task = auth_client.post("/api/v1/tasks", json={"title": "HW"}).json

    assert other_client.delete(f"/api/v1/sleep/{log['id']}").status_code == 404
    assert other_client.patch(f"/api/v1/subjects/{sub['id']}", json={"name": "pwned"}).status_code == 404
    assert (
        other_client.post(
            "/api/v1/attendance", json={"subject_id": sub["id"], "date": "2026-11-02", "status": "present"}
        ).status_code
        == 404
    )
    assert other_client.post("/api/v1/subjects", json={"semester_id": sem["id"], "name": "x"}).status_code == 404
    assert other_client.patch(f"/api/v1/tasks/{task['id']}", json={"done": True}).status_code == 404
    assert other_client.get(f"/api/v1/subjects/{sub['id']}/records").status_code == 404
    assert other_client.get("/api/v1/sleep").json["items"] == []
    assert "Maths" not in other_client.get("/api/v1/account/export").get_data(as_text=True)


def test_csrf_enforced_when_enabled():
    app = create_app("testing")
    app.config["WTF_CSRF_ENABLED"] = True
    c = app.test_client()
    r = c.post("/api/v1/auth/register", json={"name": "x", "email": "z@example.com", "password": "Passw0rd!"})
    assert r.status_code == 400 and r.json["error"]["code"] == "csrf_failed"


def test_security_headers(client):
    r = client.get("/")
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Frame-Options"] == "DENY"


def test_delete_account_cascades(app, auth_client):
    from sleep360.extensions import db
    from sleep360.models import SleepLog

    auth_client.post("/api/v1/sleep", json=night(0))
    assert auth_client.delete("/api/v1/account", json={"password": "wrong"}).status_code == 400
    assert auth_client.delete("/api/v1/account", json={"password": "Passw0rd!"}).status_code == 204
    with app.app_context():
        assert db.session.query(SleepLog).count() == 0
        assert db.session.query(User).count() == 0


def test_demo_accounts_are_isolated(client, app):
    c2 = app.test_client()
    a = client.post("/api/v1/auth/demo").json["user"]
    b = c2.post("/api/v1/auth/demo").json["user"]
    assert a["id"] != b["id"] and a["is_demo"] and b["is_demo"]
    assert client.get("/api/v1/sleep").json["items"]  # seeded
