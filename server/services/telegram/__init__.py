"""
Unified Telegram Module for Smart Parcel Locker [Person 4].

ARCHITECTURAL NOTE:
Both Outgoing Notifications (pushing OTPs, delivery proof photos, pickup notices)
and Incoming Interactive Commands (/orders, /link, /lockers, screenshot uploads)
belong to the EXACT SAME Telegram Bot identity (@SmartParcelLockerBot), powered
by the unified TELEGRAM_BOT_TOKEN.

Module Layout:
- `templates.py`: Centralized Markdown message templates (Vietnamese, branding).
- `notifier.py`: Outgoing alert dispatcher (HTTP push to Telegram users).
- `handlers.py`: Pure business rules, account linking with conflict guards, photo OCR.
- `bot.py`: Python-telegram-bot application, command router, and safe background polling.
"""
from server.services.telegram.templates import TelegramTemplates
from server.services.telegram.notifier import TelegramNotifier, notifier
from server.services.telegram.handlers import (
    PROCESSED_MEDIA_GROUPS,
    _cleanup_old_media_groups,
    link_user_to_chat,
    unlink_chat,
    get_user_orders_summary,
    check_order_detail,
    get_lockers_summary,
    get_user_profile,
    get_help_message,
    process_incoming_photo,
    process_simulated_command,
)
from server.services.telegram.bot import (
    start_telegram_polling_safe,
    stop_telegram_polling_safe,
)


class TelegramService:
    """
    Unified Telegram Service combining Outgoing Notifications and Incoming Bot Interactions.
    Both share the SAME Telegram Bot Token (single bot identity).
    """
    templates = TelegramTemplates
    notifier = notifier

    # Expose core handlers
    link_user_to_chat = staticmethod(link_user_to_chat)
    unlink_chat = staticmethod(unlink_chat)
    process_incoming_photo = staticmethod(process_incoming_photo)
    process_simulated_command = staticmethod(process_simulated_command)
    get_user_orders_summary = staticmethod(get_user_orders_summary)
    check_order_detail = staticmethod(check_order_detail)
    get_lockers_summary = staticmethod(get_lockers_summary)
    get_user_profile = staticmethod(get_user_profile)
    get_help_message = staticmethod(get_help_message)

    # Expose polling lifecycle
    start_polling = staticmethod(start_telegram_polling_safe)
    stop_polling = staticmethod(stop_telegram_polling_safe)


telegram_service = TelegramService()

__all__ = [
    "TelegramTemplates",
    "TelegramNotifier",
    "notifier",
    "TelegramService",
    "telegram_service",
    "PROCESSED_MEDIA_GROUPS",
    "_cleanup_old_media_groups",
    "link_user_to_chat",
    "unlink_chat",
    "get_user_orders_summary",
    "check_order_detail",
    "get_lockers_summary",
    "get_user_profile",
    "get_help_message",
    "process_incoming_photo",
    "process_simulated_command",
    "start_telegram_polling_safe",
    "stop_telegram_polling_safe",
]

