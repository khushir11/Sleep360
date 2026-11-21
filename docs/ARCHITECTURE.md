# Architecture

## Request flow

```
Browser ──GET /dashboard──▶ web blueprint ──▶ Jinja shell (CSRF token in <meta>)
   │
   └─fetch /api/v1/dashboard──▶ api blueprint
                                  │ @login_required (Flask-Login session)
                                  │ CSRFProtect (X-CSRFToken header on writes)
                                  │ Flask-Limiter (per-IP / per-user limits)
                                  │ parse(Schema)  ← Pydantic, extra="forbid"
                                  ▼
                               services/*  ← pure functions + user-scoped queries
                                  │
                       ┌──────────┼──────────────┐
                       ▼          ▼              ▼
                  SQLAlchemy   ml/predictor   Anthropic API
                  (Postgres)   (joblib model)  (optional)
```

### Layers

| Layer | Responsibility | Rule |
|---|---|---|
| `api/` | HTTP: parse, authorise, call a service, serialise | No business logic. Errors use one JSON shape: `{"error": {code, message, details}}`. |
| `schemas.py` | Input validation | Every write goes through a Pydantic model with `extra="forbid"`, so mass-assignment (e.g. `is_demo: true`) is impossible. |
| `services/` | Business logic | Pure where possible (e.g. `attendance.classes_needed`, `planner.build_plan`), so it's testable with plain objects. |
| `services/queries.py` | Data access | All user-owned reads go through helpers that filter by `user_id`. `get_owned()` returns **404** for other users' IDs, never revealing that the row exists. |
| `ml/` | Features, training, inference | `features.build_features` is shared by the synthetic generator, DB training and live inference. |
| `web/` + `static/` | UI | Page shells and ES modules. No inline JS or CSS, because of the strict CSP. |

## Data model

```mermaid
erDiagram
  users ||--o{ sleep_logs : logs
  users ||--o{ semesters : has
  semesters ||--o{ subjects : contains
  users ||--o{ subjects : owns
  subjects ||--o{ attendance_records : has
  users ||--o{ tasks : plans
  subjects ||--o{ tasks : "optional"
  users ||--o{ study_sessions : records
  tasks ||--o{ study_sessions : "optional"
  users ||--o{ risk_assessments : "1 per day"
  users ||--o{ chat_messages : sends
  users ||--o{ notifications : receives
  users ||--o{ achievements : earns

  users { int id PK; string email UK; string password_hash; float sleep_goal_hours; time target_wake_time; float attendance_target; string timezone; bool is_demo }
  sleep_logs { int id PK; int user_id FK; date date; datetime bedtime; datetime wake_time; int quality; int daytime_sleepiness; int stress; int screen_minutes_before_bed; bool caffeine_after_2pm; int exercise_minutes; enum source }
  semesters { int id PK; int user_id FK; date start_date; date end_date; bool is_active }
  subjects { int id PK; int user_id FK; int semester_id FK; float classes_per_week; float target_override; int initial_conducted; int initial_attended }
  attendance_records { int id PK; int subject_id FK; date date; int period; enum status }
  tasks { int id PK; int user_id FK; int subject_id FK; enum kind; datetime due_at; int estimated_minutes; int priority; bool done }
  study_sessions { int id PK; int user_id FK; int task_id FK; datetime started_at; int duration_minutes; int focus }
  risk_assessments { int id PK; int user_id FK; date date; float sleep_score; float fatigue_probability; string model_version; json details }
  notifications { int id PK; int user_id FK; string dedupe_key; datetime read_at }
```

**Constraints and indexes worth knowing:**
- `sleep_logs (user_id, date)` is **unique**: one night per wake date, so logging is an idempotent upsert. A composite index serves the range queries every page makes.
- `attendance_records (subject_id, date, period)` is unique: re-marking a class updates it, and `period` allows two lectures on the same day.
- `risk_assessments (user_id, date)` is unique: an upsert snapshot per day.
- `notifications (user_id, dedupe_key)` is unique: the scanner is idempotent, and a race between two scans is resolved by the constraint (an `IntegrityError` is caught).
- `tasks (user_id, done, due_at)` is indexed for the open-tasks query.
- All FKs use `ON DELETE CASCADE` (or `SET NULL` for optional links), and the ORM cascades too, so account deletion removes everything on every backend.

**Derived, not stored:** sleep duration, attendance %, classes needed. These are computed from source rows, so they can never drift. The one deliberate exception is `risk_assessments`, a snapshot that makes changes over time explainable and lets old predictions keep their `model_version`.

**Opening balances:** `subjects.initial_conducted/attended` let a student join mid-semester without back-filling 40 classes. Attendance = opening balance + marked records.

**Time handling:** wall-clock times are stored as naive local datetimes, which matches how students think about sleep, plus a per-user IANA `timezone` used to work out "today". Bedtimes are compared on a minutes-after-18:00 scale, so 23:30 and 00:30 are 60 minutes apart, not 23 hours.

## Migrations

Alembic (via Flask-Migrate, `render_as_batch=True` so ALTERs work on SQLite too):
- `2b7001f82fd8` initial schema
- `a4d0e7e5d70a` widens `risk_assessments.model_version` 40 → 80. This was found by running against Postgres: SQLite doesn't enforce `VARCHAR(n)`.

CI runs `flask db upgrade && flask db check` against Postgres 16 to catch model/migration drift.

## Data pipelines

**Assessment pipeline (on every write to sleep logs):** `after_log_change(day)` recomputes `day … day+7`, because a night influences the 7-day window features of the following week. Settings changes (goal, wake time) recompute the last 30 days. `flask assess backfill` recomputes everything after a model retrain.

**CSV import (`services/importer.py`):** extract (decode UTF-8/Latin-1, sniff delimiter) → normalise (header aliases, 8 datetime formats, time-only + date column, 0–100 → 1–10 scaling, yes/no parsing) → validate (the same `SleepLogIn` schema as the API) → deduplicate within the file (last row per date wins) → load (one query for existing rows, upsert with optional overwrite) → recompute assessments for the affected range. It's one transaction with per-row error reporting and limits of 2 MB / 2,000 rows.

**Training pipeline (`ml/train.py`):** simulate or load → GroupKFold evaluation of 3 models + 2 baselines → selection rule → permutation importance on held-out groups → refit (isotonic calibration for trees) → `fatigue_model.joblib` + `model_card.json`.

## Security

| Threat | Mitigation |
|---|---|
| Credential theft | Werkzeug scrypt hashes. A password policy (8+ chars, a letter and a digit). Identical errors and similar timing for unknown email vs wrong password (dummy hash check). |
| Brute force | Flask-Limiter: login 10/min and 50/h per IP. Register 10/h. Demo 5/h. Chat 20/min per user. |
| Session attacks | HttpOnly, SameSite=Lax and Secure cookies. `session.clear()` on login (prevents fixation). Flask-Login `session_protection="strong"`. |
| CSRF | Flask-WTF on all state-changing requests, including JSON (header token). |
| XSS | Jinja autoescape. JS inserts user text with `textContent` or `esc()`. The assistant's Markdown renderer escapes first. CSP `script-src 'self'` with no inline scripts. |
| IDOR | `get_owned()` everywhere, returning 404 for foreign IDs. Tests cover cross-user access on every resource type. |
| Mass assignment | Pydantic `extra="forbid"`. |
| Open redirect | The login `next` parameter is restricted to same-site paths. |
| Secrets | Env vars only. `.env` is git-ignored and the app refuses to start without `SECRET_KEY`. The old committed SQLite DB was removed. |
| Clickjacking / sniffing | `X-Frame-Options: DENY`, `frame-ancestors 'none'`, `nosniff`, and HSTS behind HTTPS. |
| LLM data exposure | Only aggregates go to the provider (no email, no notes). A user toggle. Crisis messages never reach the LLM. |
