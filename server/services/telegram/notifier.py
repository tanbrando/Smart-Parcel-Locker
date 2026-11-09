"""
Telegram Outgoing Notification Service [Person 4].
Sends instant pickup OTPs, locker status alerts, and delivery photos to recipients.
Operates using the unified TELEGRAM_BOT_TOKEN.
"""
import io
import base64
import logging
import requests
from typing import Optional

from server.core.config import settings
from server.services.telegram.templates import TelegramTemplates

logger = logging.getLogger("server.services.telegram.notifier")


class TelegramNotifier:
    """Dispatches real-time alerts via Telegram Bot API (Outgoing face of the Bot)."""

    def __init__(self, bot_token: Optional[str] = settings.TELEGRAM_BOT_TOKEN):
        self.bot_token = bot_token

    def send_message(self, chat_id: Optional[int], text: str) -> bool:
        """Sends markdown formatted Telegram message."""
        if not self.bot_token or not chat_id:
            logger.info("[Telegram Notifier MOCK] Chat ID: %s | Message:\n%s", chat_id, text)
            return True

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }

        try:
            resp = requests.post(url, json=payload, timeout=5.0)
            if resp.status_code == 200:
                logger.info("Telegram notification delivered to %s", chat_id)
                return True
            else:
                logger.error("Failed to send Telegram msg: %s", resp.text)
                return False
        except requests.RequestException as exc:
            logger.error("Telegram network failure: %s", exc)
            return False

    def send_photo(self, chat_id: Optional[int], caption: str, photo_base64: str) -> bool:
        """Sends delivery proof photo with caption via Telegram."""
        if not self.bot_token or not chat_id:
            logger.info("[Telegram Notifier MOCK Photo] Chat ID: %s | Caption: %s", chat_id, caption)
            return True

        try:
            image_data = base64.b64decode(photo_base64)
            url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"
            files = {"photo": ("delivery_proof.jpg", io.BytesIO(image_data), "image/jpeg")}
            data = {"chat_id": chat_id, "caption": caption, "parse_mode": "Markdown"}

            resp = requests.post(url, data=data, files=files, timeout=8.0)
            return resp.status_code == 200
        except Exception as exc:
            logger.error("Failed to send photo via Telegram: %s", exc)
            return self.send_message(chat_id, caption)

    def notify_parcel_deposited(
        self,
        chat_id: Optional[int],
        tracking_number: str,
        locker_number: int,
        otp_code: str,
        delta_weight: int,
        image_base64: Optional[str] = None,
    ) -> bool:
        """Sends pickup notification containing locker number, measured weight, and 6-digit OTP."""
        message = TelegramTemplates.parcel_deposited(
            tracking_number=tracking_number,
            locker_number=locker_number,
            delta_weight=delta_weight,
            otp_code=otp_code,
            valid_hours=settings.OTP_VALID_HOURS,
        )

        if image_base64:
            return self.send_photo(chat_id, message, image_base64)
        return self.send_message(chat_id, message)

    def notify_parcel_collected(self, chat_id: Optional[int], tracking_number: str, locker_number: int) -> bool:
        """Sends pickup confirmation."""
        message = TelegramTemplates.parcel_collected(
            tracking_number=tracking_number,
            locker_number=locker_number,
        )
        return self.send_message(chat_id, message)


notifier = TelegramNotifier()

