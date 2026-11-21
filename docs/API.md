# REST API v1

Base path: `/api/v1`. JSON in and out. Auth uses a session cookie, set by `/auth/login`, `/auth/register` or `/auth/demo`. Every non-GET request must send `X-CSRFToken` (read it from `<meta name="csrf-token">`).

Errors always look like:
```json
{ "error": { "code": "validation_error", "message": "Wake time must be after bedtime", "details": [{ "field": "wake_time", "message": "..." }] } }
```
Codes: `bad_request` 400, `csrf_failed` 400, `unauthorized` 401, `invalid_credentials` 401, `not_found` 404 (also returned for other users' IDs), `email_taken` 409, `validation_error` 422, `rate_limited` 429, `model_unavailable` 503.

## Auth
| Method | Path | Body | Notes |
|---|---|---|---|
| POST | `/auth/register` | `{name, email, password}` | 201 and logs in. 10/h per IP. |
| POST | `/auth/login` | `{email, password, remember?}` | 10/min per IP |
| POST | `/auth/demo` | – | Creates an isolated demo user with sample data. 5/h. |
| POST | `/auth/logout` | – | |
| GET | `/auth/me` | – | |

## Sleep
| Method | Path | Notes |
|---|---|---|
| GET | `/sleep?start=&end=` | Default: last 30 days. Max range 1 year. |
| POST | `/sleep` | `{bedtime, wake_time, quality, daytime_sleepiness?, stress?, screen_minutes_before_bed?, caffeine_after_2pm?, exercise_minutes?, notes?}`. Upsert by wake date: 201 if created, 200 if updated. Returns `{log, assessment, change}`. |
| DELETE | `/sleep/{id}` | Recomputes affected assessments. |
| POST | `/sleep/import` | multipart `file` (CSV ≤ 2 MB) + `overwrite=true\|false`. Returns a row-level `report`. |
| GET | `/sleep/bedtime-plan` | Bedtime, wind-down, screens-off, last caffeine, cycle options |

## Attendance
| Method | Path | Notes |
|---|---|---|
| GET | `/semesters` | With per-semester overall stats |
| POST | `/semesters` | `{name, start_date, end_date, is_active}`. Creating an active one deactivates the others. |
| POST | `/semesters/{id}/activate` · DELETE `/semesters/{id}` | |
| GET | `/attendance?semester_id=` | Subjects with `percentage, status, classes_needed, safe_skips, remaining_classes, max_achievable, projected_end, recent_rate`, plus weekly and monthly series |
| POST | `/subjects` | `{semester_id, name, code?, classes_per_week, target_override?, initial_conducted, initial_attended, color}` |
| PATCH / DELETE | `/subjects/{id}` | Partial update |
| GET | `/subjects/{id}/records` | |
| POST | `/attendance` | `{subject_id, date, status: present\|absent\|cancelled, period?}`. Upsert per slot. |
| DELETE | `/attendance/{id}` | |
| GET | `/attendance/simulate?subject_id=&attend=&miss=` | What-if |

`status` is one of: `safe` (≥ target + 5), `warning`, `shortage`, `critical` (target unreachable even if every remaining class is attended), `no_data`.

## Planner
| Method | Path | Notes |
|---|---|---|
| GET | `/tasks?status=open\|done\|all` | Includes `remaining_minutes` (estimate − logged study) |
| POST | `/tasks` · PATCH / DELETE `/tasks/{id}` | `done: true` sets `completed_at` |
| GET / POST | `/study-sessions` · DELETE `/study-sessions/{id}` | `{started_at, duration_minutes, task_id?, subject_id?, focus?}` |
| GET | `/planner?date=&start=HH:MM&max_minutes=` | Blocks (focus / break / wind_down), unscheduled work, notes |
| GET | `/productivity?days=` | Daily minutes, by subject, weekly goal, sleep↔study correlation (n ≥ 10) |

## Insights
| Method | Path | Notes |
|---|---|---|
| GET | `/dashboard` | Everything for the dashboard in one call. Also runs the notification scan. |
| GET | `/analytics?days=7..180` | Series, weekday pattern, weekly table, attendance trend, study |
| GET | `/recommendations` | `[{id, category, priority, title, body, actions[], why, evidence, tone}]` |
| GET | `/assessment/latest` | Latest assessment plus a `change` explanation |
| GET | `/achievements` | Streaks, challenge, badges (idempotent awarding) |
| GET | `/model` | **Public** model card |
| GET | `/notifications` · POST `/notifications/read` `{ids?}` | |

## Assistant
| Method | Path | Notes |
|---|---|---|
| GET | `/assistant/messages` | History plus `ai_configured`, `ai_enabled` |
| POST | `/assistant/messages` | `{message}` → `{message: {content, provider: anthropic\|fallback\|safety}}`. 20/min per user. |
| DELETE | `/assistant/messages` | Clear history |

## Account & reports
| Method | Path | Notes |
|---|---|---|
| GET / PATCH | `/account` | Goals, institutional target, timezone, AI toggle. Changing the goal or wake time recomputes 30 days of scores. |
| POST | `/account/password` | `{current_password, new_password}` |
| GET | `/account/export` | Full JSON export (download) |
| DELETE | `/account` | `{password}` (not needed for demo). Cascades. |
| GET | `/reports/weekly.pdf?end=YYYY-MM-DD` | PDF report |
| GET | `/health` | DB ping for load balancers |
