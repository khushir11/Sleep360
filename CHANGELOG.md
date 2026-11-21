# Changelog

## 2.0.0: Student wellness platform rewrite

### Bugs and issues fixed from 1.x
**Security**
- Login accepted any email with **no password**, so anyone could open any student's dashboard. Replaced with hashed-password auth (scrypt), session-fixation protection and rate limiting.
- `app.secret_key` was hard-coded in source. Now read from `SECRET_KEY`, and the app refuses to start without it.
- `data/sleep360.db` (with demo names and emails) was committed. Removed, and `*.db` / `instance/` are now git-ignored.
- No CSRF protection on state-changing endpoints. Added Flask-WTF CSRF, including on JSON requests.
- `/api/platform-stats` and the cohort pages aggregated every student's data for any visitor. Removed. Each user now sees only their own data.

**Correctness and honesty**
- The About page claimed the model was *"validated against actual student attendance records… Pearson r = 0.78"*. It was an untrained hand-weighted formula. Claim removed and replaced by a real, documented pipeline and model card.
- The Research page fell back to invented statistics (28%, 15%, 22%, 18%) when data was missing. Removed.
- The home page showed fake defaults (7.2h sleep, 78.4% attendance) when no data existed. Replaced with proper empty states.
- "Sleeping after midnight 5 days/week" was inferred from one yes/no field. Timing is now computed from actual bedtimes.
- Unsupported claims ("reduces cognition by 25%", "exercise improves sleep by 65%") were replaced with sourced, cautious guidance.

**Robustness**
- Missing JSON fields raised `KeyError` → 500. All inputs are now validated with Pydantic, with field-level 422 errors.
- Each submission stored a full snapshot with no notion of dates, so there was no history or trends. Replaced by daily logs (unique per night) and per-class attendance.
- The latest prediction was ordered by a second-resolution timestamp, so ties picked an arbitrary row. Predictions are now keyed by date.
- SQLite on Render's ephemeral disk lost all data on every deploy. Added Postgres support with Alembic migrations, plus a Render Blueprint.
- README screenshots pointed to a missing `screenshots/` folder. New screenshots are in `docs/screenshots/`.
- `flask-cors` was an unused dependency. Removed.

### New
- App factory, blueprints, versioned REST API, service layer, SQLAlchemy 2.0 models (11 tables), Alembic migrations.
- Daily sleep logging, CSV import pipeline, bedtime planner, transparent sleep score with change explanations.
- Subject-wise attendance with opening balances, per-subject targets, classes needed, safe skips, forecasts and a what-if simulator.
- Sleep-friendly study planner, tasks, focus timer, study-hour tracking, productivity insights.
- Recommendation engine (15 rules), analytics (2W/30D/90D), weekly PDF report, JSON export, account deletion.
- ML pipeline: synthetic generator, shared feature code, LR/RF/GB comparison with GroupKFold, baselines, calibration, permutation importance, per-prediction explanations, model card, DB retraining path.
- Claude assistant with grounded context, crisis-safety layer and deterministic fallback.
- Notifications (in-app + browser), streaks, consistency challenge, badges, isolated demo sandboxes.
- Redesigned responsive UI (light/dark), strict CSP, accessibility (labels, focus states, ARIA live regions, reduced motion).
- 55 tests (88% coverage), ruff, GitHub Actions CI with a Postgres service, Dockerfile, Playwright smoke test.

### Migrations
- `2b7001f82fd8`: initial schema
- `a4d0e7e5d70a`: widen `risk_assessments.model_version` to 80 chars (found by testing on Postgres)
