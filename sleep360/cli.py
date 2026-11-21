"""Flask CLI commands: ``flask ml train``, ``flask demo create|cleanup``, ``flask notifications scan``, ``flask assess backfill``."""

from __future__ import annotations

import json

import click
from flask import Flask, current_app
from flask.cli import AppGroup
from sqlalchemy import select

from .extensions import db


def register_cli(app: Flask) -> None:
    ml = AppGroup("ml", help="Machine-learning pipeline")
    demo = AppGroup("demo", help="Demo accounts")
    notif = AppGroup("notifications", help="Notification jobs")
    assess = AppGroup("assess", help="Assessment jobs")

    @ml.command("train")
    @click.option("--source", type=click.Choice(["synthetic", "db"]), default="synthetic")
    @click.option("--students", default=400, show_default=True, help="Synthetic students to simulate")
    @click.option("--seed", default=42, show_default=True)
    def ml_train(source: str, students: int, seed: int):
        """Train, compare and save the fatigue model (writes model_card.json too)."""
        from .ml.predictor import reset_cache
        from .ml.synthetic import SimConfig
        from .ml.train import train

        card = train(
            source=source, out_path=current_app.config["MODEL_PATH"], seed=seed, sim=SimConfig(n_students=students, seed=seed)
        )
        reset_cache()
        click.echo(f"Selected: {card['selected_model']}  ({card['version']})")
        for name, m in card["comparison"].items():
            click.echo(
                f"  {name:28s} ROC-AUC {m['roc_auc']['mean']:.3f} ± {m['roc_auc']['std']:.3f}   "
                f"AP {m['avg_precision']['mean']:.3f}   Brier {m['brier']['mean']:.3f}"
            )
        click.echo(card["data_disclaimer"])

    @ml.command("card")
    def ml_card():
        from .ml.predictor import get_predictor

        p = get_predictor(current_app.config["MODEL_PATH"])
        click.echo(json.dumps(p.card if p else {"error": "model not loaded"}, indent=2))

    @demo.command("create")
    @click.option("--email", default="demo@sleep360.dev", show_default=True)
    @click.option("--password", default="Demo12345", show_default=True)
    def demo_create(email: str, password: str):
        """Create a sample account you can log into locally (data is flagged as demo)."""
        from .models import User
        from .services.demo import create_demo_user

        existing = db.session.scalar(select(User).where(User.email == email))
        if existing:
            db.session.delete(existing)
            db.session.commit()
        u = create_demo_user(email=email, seed=7)
        u.set_password(password)
        db.session.commit()
        click.echo(f"Demo account ready: {email} / {password}")

    @demo.command("cleanup")
    @click.option("--older-than", default=2, show_default=True, help="days")
    def demo_cleanup(older_than: int):
        from .services.demo import cleanup

        click.echo(f"Removed {cleanup(older_than)} demo account(s)")

    @notif.command("scan")
    def notif_scan():
        """Generate notifications for all users (run from a scheduler, e.g. hourly)."""
        from .models import User
        from .services.notifications import scan

        n = sum(scan(u) for u in db.session.scalars(select(User)))
        click.echo(f"Created {n} notification(s)")

    @assess.command("backfill")
    def assess_backfill():
        """Recompute every assessment (run after retraining the model)."""
        from .ml.predictor import reset_cache
        from .models import User
        from .services.assessments import reassess_range
        from .services.queries import sleep_logs

        reset_cache()
        for u in db.session.scalars(select(User)):
            logs = sleep_logs(u)
            if logs:
                reassess_range(u, logs[0].date, logs[-1].date)
        click.echo("Done")

    for g in (ml, demo, notif, assess):
        app.cli.add_command(g)
