"""
Backward-compatible shim for TelegramNotifier [Person 4].
Delegates directly to the unified server.services.telegram module.
"""
from server.services.telegram.notifier import TelegramNotifier, notifier

__all__ = ["TelegramNotifier", "notifier"]
