"""
Backward-compatible shim for Telegram Bot Service [Person 4].
Delegates directly to the unified server.services.telegram module.
Preserves all historical entry points, mock interfaces, and test fixtures.
"""
from server.db.session import SessionLocal
from server.services.telegram import (
    TelegramTemplates,
    TelegramNotifier,
    notifier,
    TelegramService,
    telegram_service,
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
    start_telegram_polling_safe,
    stop_telegram_polling_safe,
)

__all__ = [
    "SessionLocal",
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
