# Contributing

## Setup
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # set SECRET_KEY, SESSION_COOKIE_SECURE=0
flask --app wsgi db upgrade && flask --app wsgi demo create
flask --app wsgi run
```

## Workflow
- Branch from `main`: `feat/…`, `fix/…`, `docs/…`.
- Put business logic in `sleep360/services/` and keep routes thin. Every new write endpoint needs a Pydantic schema in `schemas.py`.
- All reads of user data go through `services/queries.py` (ownership checks live there).
- Changed a model? Run `flask --app wsgi db migrate -m "describe change"`, review the generated file and commit it.
- Changed `ml/features.py`? Retrain (`flask --app wsgi ml train`) and commit the new artifact and `model_card.json`.
- Frontend: no inline `<script>`, `style=` or `onclick` (the CSP blocks them). Insert user text with `textContent` or `esc()`.

## Before opening a PR
```bash
ruff check . && ruff format --check .
pytest --cov=sleep360
```
Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`).
