"""
Telegram Bot Notification Service [Person 4].
Sends instant pickup OTPs and locker status alerts to recipients.
"""
import logging
import requests
from typing import Optional

from server.core.config import settings

logger = logging.getLogger("server.services.notifier")


class TelegramNotifier:
    """Dispatches real-time alerts via Telegram Bot API."""

    def __init__(self, bot_token: Optional[str] = settings.TELEGRAM_BOT_TOKEN):
        self.bot_token = bot_token

    def send_message(self, chat_id: str, text: str) -> bool:
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

    def notify_parcel_deposited(
        self, chat_id: str, tracking_number: str, locker_id: int, otp_code: str
    ) -> bool:
        """Sends pickup notification containing locker number and 6-digit OTP."""
        message = (
            f"📦 *Bưu Kiện Đã Được Giao Đến Smart Locker!*\n\n"
            f"• *Mã vận đơn:* `{tracking_number}`\n"
            f"• *Ngăn tủ số:* *{locker_id}*\n"
            f"• *Mã OTP lấy hàng:* `{otp_code}`\n"
            f"• *Thời hạn hiệu lực:* {settings.OTP_VALID_MINUTES} phút\n\n"
            f"👉 Đến tủ thông minh, nhập mã OTP trên bàn phím để nhận kiện hàng."
        )
        return self.send_message(chat_id, message)

    def notify_parcel_retrieved(self, chat_id: str, tracking_number: str, locker_id: int) -> bool:
        """Sends pickup confirmation."""
        message = (
            f"✅ *Nhận Hàng Thành Công!*\n\n"
            f"Bưu kiện `{tracking_number}` tại ngăn tủ *{locker_id}* đã được lấy đi.\n"
            f"Cảm ơn bạn đã sử dụng Smart Parcel Locker!"
        )
        return self.send_message(chat_id, message)


notifier = TelegramNotifier()

