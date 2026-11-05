"""
Security and OTP Engine Module [Person 4].
Generates cryptographically random numeric OTPs and validates expiration.
"""
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Tuple

from server.core.config import settings


def generate_otp(length: int = settings.OTP_LENGTH) -> Tuple[str, datetime]:
    """
    Generates a secure numeric OTP and its expiration timestamp.
    Returns: (otp_code, expires_at)
    """
    digits = string.digits
    otp_code = "".join(secrets.choice(digits) for _ in range(length))
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.OTP_VALID_MINUTES)
    return otp_code, expires_at


def is_otp_expired(expires_at: datetime) -> bool:
    """Checks if the given timestamp has passed."""
    if expires_at.tzinfo is None:
        return datetime.utcnow() > expires_at
    return datetime.now(timezone.utc) > expires_at
