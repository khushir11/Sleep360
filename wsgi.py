"""WSGI entry point: ``gunicorn wsgi:app`` (production) or ``flask --app wsgi run`` (local)."""

from dotenv import load_dotenv

load_dotenv()

from sleep360 import create_app  # noqa: E402

app = create_app()
