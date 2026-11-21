# Interview guide: explaining Sleep360

Short answers to the questions interviewers actually ask, with pointers to the code.

## 30-second pitch
"Sleep360 is a Flask + Postgres wellness platform for college students. It combines daily sleep logs, subject-wise attendance and a study planner. The core is a layered backend: a versioned REST API, Pydantic validation, a pure-Python service layer and Alembic migrations. On top of that sit an ML pipeline comparing logistic regression, random forest and gradient boosting with grouped cross-validation, and a Claude-powered assistant grounded in the user's data with a safety layer and a fallback. I was deliberate about honesty: the model is trained on simulated data, and the app says so everywhere."

## Architecture
**Why Flask and not Django/FastAPI?** The project started in Flask and was deployed on Render. Flask's blueprints, app factory and extensions gave me exactly the pieces I needed (SQLAlchemy, Login, WTF-CSRF, Limiter, Migrate) without fighting a framework. FastAPI would have suited an API-only service, but I also serve pages and use session auth with CSRF, which is simpler in Flask.

**Why not a React SPA?** It would add a Node build, a second deployable and token auth for little user benefit. Pages are server-rendered shells and the browser calls the JSON API, so a mobile app could reuse the API unchanged. → `sleep360/web/`, `sleep360/api/`

**How are routes kept thin?** Routes parse (`api.parse(Schema)`), authorise (`queries.get_owned`) and call a service. Logic like `classes_needed()` or `build_plan()` is plain Python, so it's tested without HTTP. → `services/attendance.py`, `tests/test_attendance.py`

## Database
**Walk me through the schema.** Eleven tables, all owned by `users`. Two design points stand out:
1. `sleep_logs` has a unique `(user_id, date)` constraint, so logging is an idempotent upsert keyed by wake date.
2. Attendance is per-class records plus an opening balance on `subjects`, so mid-semester users don't back-fill. Percentages are computed, never stored. → `docs/ARCHITECTURE.md`

**Why store `risk_assessments` if you can recompute?** For explainability over time. "Why did my score drop?" is a diff between two snapshots, and each row records the `model_version` that produced it.

**A bug you found?** `model_version` was `VARCHAR(40)`, and the generated version string was 42 characters. SQLite doesn't enforce lengths, so tests passed. Running against real Postgres failed. I widened it with an Alembic migration and added `db upgrade` + `db check` on Postgres to CI. Lesson: test against the production database engine.

**Indexes?** Composite `(user_id, date)` on logs (every page reads a date range for one user), `(user_id, done, due_at)` on tasks, and `(user_id, started_at)` on study sessions.

## Data engineering
**Describe the CSV pipeline.** Extract (encoding + delimiter sniffing), normalise (header aliases, 8 datetime formats, 0–100 → 1–10 scaling), validate with the *same* schema as the API, deduplicate within the file, upsert in one transaction, then recompute derived assessments for the affected window. Per-row errors are returned with line numbers. → `services/importer.py`

**Why recompute 7 days after an edit?** Features use a 7-day window, so editing Monday changes the features for Tuesday through the following Monday.

## Machine learning
**Why GroupKFold?** Each simulated student contributes about 53 rows with persistent traits. A random split leaks those traits into the test set and inflates scores. Grouping by student measures generalisation to *new* students.

**Why did logistic regression win?** All three models scored within one standard deviation (~0.74 AUC). My rule prefers the simpler model within 0.005, because LR is calibrated by construction and easier to explain. Trees capture the hinge and interaction, but the gain is smaller than the noise.

**Isn't training on synthetic data pointless?** The data can't tell us anything about real students, and I say that explicitly. What it does is exercise the full pipeline: feature code shared with serving, grouped CV, baselines, calibration, explanations, versioning. It also gives the app a cold-start model. The app collects a real label (daytime sleepiness), so `ml train --source db` can retrain on real data with the same code.

**How do explanations work?** Each feature is replaced in turn with the training median, and the change in probability is measured. It's model-agnostic and easy to read, but not additive like SHAP. I chose it to avoid a heavy dependency, and the UI says it's approximate.

**What would you do with real data?** Collect it with consent. Check label quality (are sleepiness ratings consistent?). Look at per-user calibration. Consider per-user baselines (mixed-effects model). Monitor drift. Run a fairness review if any demographic data were ever collected (it isn't now).

## AI integration
**How is the assistant grounded?** `build_context()` sends a compact JSON of the user's aggregates (7-day stats, score components, attendance maths, upcoming tasks) in the system prompt, and the prompt tells the model to quote those numbers. Email and free-text notes are excluded, and a test asserts it.

**Failure modes?** No key, timeout, rate limit or empty response all fall back to a deterministic intent engine that answers from the same context. The user always gets a useful reply, and the response records which provider answered.

**Safety?** A regex check for crisis language runs *before* any model call and returns a fixed, human-written message with Tele-MANAS (14416) and emergency numbers. A test asserts the LLM is never invoked for those messages.

## Security
Scrypt hashes; session fixation prevention; CSRF on JSON; rate limits; `extra="forbid"` against mass assignment; 404 on foreign IDs (IDOR tests for every resource type); strict CSP with vendored assets; same-site-only login redirects; secrets only from env.

**What did you fix from the original?** Login took only an email (no password), so anyone could open anyone's dashboard. The secret key was hard-coded, the DB with emails was committed to the repo, and there was no CSRF protection or input validation (missing fields caused 500s).

## Testing
55 pytest tests with 88% coverage: unit tests (attendance maths with minimality checks, sleep scoring, planner constraints), API tests (auth, validation, upserts, cross-user isolation), ML tests (determinism, beats baselines, monotonicity), mocked LLM tests, plus a Playwright journey across 9 user steps. CI runs ruff, pytest and Postgres migrations.

**A testing bug you hit?** Two test clients appeared to share a logged-in user. The fixture kept an app context open, so Flask reused it across requests and Flask-Login's cached user in `g` leaked between clients. Fixing the fixture showed that isolation was actually correct.

## What I'd do next
Web Push notifications (VAPID), Fitbit/Google Fit OAuth sync through the existing importer, Redis for rate limits and caching, background jobs (RQ/Celery) for the notification scan, and an opt-in real-data study to retrain the model.
