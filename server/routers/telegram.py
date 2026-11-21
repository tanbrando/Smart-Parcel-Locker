"""
Telegram Router [Person 4].
Provides status, webhook listener, and simulation endpoints for interactive Telegram bot testing.
"""
import base64
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from sqlalchemy.orm import Session

from server.core.config import settings
from server.db.session import get_db
from server.db.models import User
from server.services.telegram import process_simulated_command

router = APIRouter(prefix="/telegram", tags=["Telegram Bot"])


class TelegramCommandSimulationRequest(BaseModel):
    chat_id: int
    text: Optional[str] = ""
    photo_base64: Optional[str] = None
    filename: Optional[str] = "screenshot.jpg"
    media_group_id: Optional[str] = None


@router.get("/status")
def get_bot_status(db: Session = Depends(get_db)):
    """Returns Telegram Bot connection status and linked user statistics."""
    linked_users_count = db.query(User).filter(User.telegram_chat_id.isnot(None)).count()
    total_users_count = db.query(User).count()

    return {
        "bot_configured": bool(settings.TELEGRAM_BOT_TOKEN),
        "bot_username": settings.TELEGRAM_BOT_USERNAME,
        "polling_enabled": settings.ENABLE_TELEGRAM_BOT_POLLING,
        "linked_users": linked_users_count,
        "total_users": total_users_count,
    }


@router.post("/simulate-command")
def simulate_telegram_command(req: TelegramCommandSimulationRequest):
    """
    Simulates a Telegram user interaction (command or photo) without requiring a live Telegram bot.
    Used by Web Dashboard, test suites, and team members (Persons 1, 2, 3).
    """
    photo_bytes = None
    if req.photo_base64:
        try:
            photo_bytes = base64.b64decode(req.photo_base64)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid photo_base64 encoding")

    result = process_simulated_command(
        chat_id=req.chat_id,
        text=req.text or "",
        photo_bytes=photo_bytes,
        filename=req.filename or "screenshot.jpg",
        media_group_id=req.media_group_id,
    )
    return result


@router.post("/webhook")
async def telegram_webhook(update: dict = Body(...)):
    """Webhook listener for Telegram updates when deployed behind HTTPS."""
    # Webhook handling can extract message/photo and delegate to process_simulated_command
    msg = update.get("message", {})
    chat_id = msg.get("chat", {}).get("id")
    text = msg.get("text", "")

    if chat_id and text:
        res = process_simulated_command(chat_id=chat_id, text=text)
        return {"ok": True, "result": res}

    return {"ok": True}

