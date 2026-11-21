from __future__ import annotations

from flask import current_app
from flask_login import current_user, login_required
from sqlalchemy import delete, select

from ..extensions import db, limiter
from ..models import ChatMessage
from ..schemas import ChatIn
from ..services.assistant import respond
from . import bp, parse


def _history(limit: int = 30) -> list[ChatMessage]:
    rows = db.session.scalars(
        select(ChatMessage)
        .where(ChatMessage.user_id == current_user.id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(limit)
    )
    return list(reversed(list(rows)))


@bp.get("/assistant/messages")
@login_required
def chat_history():
    return {
        "items": [m.to_dict() for m in _history()],
        "ai_configured": bool(current_app.config.get("ANTHROPIC_API_KEY")),
        "ai_enabled": current_user.ai_assistant_enabled,
    }


@bp.post("/assistant/messages")
@login_required
@limiter.limit("20 per minute; 200 per day", key_func=lambda: f"chat:{current_user.get_id()}")
def chat():
    data = parse(ChatIn)
    history = _history(10)
    reply = respond(current_user, data.message, history)
    um = ChatMessage(user_id=current_user.id, role="user", content=data.message)
    am = ChatMessage(user_id=current_user.id, role="assistant", content=reply.content, provider=reply.provider)
    db.session.add_all([um, am])
    db.session.commit()
    return {"message": am.to_dict()}, 201


@bp.delete("/assistant/messages")
@login_required
def clear_chat():
    db.session.execute(delete(ChatMessage).where(ChatMessage.user_id == current_user.id))
    db.session.commit()
    return "", 204
