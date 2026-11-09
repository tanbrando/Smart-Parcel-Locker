"""
Security, OTP Engine and Rate Limiter Module [Person 4].
Generates cryptographically random numeric OTPs and enforces rate limiting on verification attempts.
"""
import time
import secrets
import string
import logging
from datetime import datetime, timedelta, timezone
from typing import Tuple, Optional

from server.core.config import settings

logger = logging.getLogger("server.core.security")


def generate_otp(length: int = settings.OTP_LENGTH, hours_valid: int = settings.OTP_VALID_HOURS) -> Tuple[str, datetime]:
    """
    Generates a secure numeric OTP and its expiration timestamp.
    Returns: (otp_code, expires_at)
    """
    digits = string.digits
    otp_code = "".join(secrets.choice(digits) for _ in range(length))
    expires_at = datetime.now(timezone.utc) + timedelta(hours=hours_valid)
    return otp_code, expires_at


def is_otp_expired(expires_at: Optional[datetime]) -> bool:
    """Checks if the given timestamp has passed."""
    if not expires_at:
        return False
    if expires_at.tzinfo is None:
        return datetime.now(timezone.utc) > expires_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) > expires_at


class OtpRateLimiter:
    """
    In-memory rate limiter tracking consecutive failed OTP entries.
    Allows up to MAX_OTP_ATTEMPTS before temporary lockout.
    """

    def __init__(self, max_attempts: int = settings.MAX_OTP_ATTEMPTS, lockout_seconds: int = settings.LOCKOUT_SECONDS):
        self.max_attempts = max_attempts
        self.lockout_seconds = lockout_seconds
        self.failed_attempts = 0
        self.locked_until = 0.0

    def is_locked(self) -> bool:
        """Returns True if the system is currently locked out."""
        if self.locked_until and time.time() < self.locked_until:
            return True
        if self.locked_until and time.time() >= self.locked_until:
            # Lockout expired, reset
            self.reset()
        return False

    def record_failure(self) -> Tuple[int, bool]:
        """
        Records a failed attempt.
        Returns: (remaining_attempts, is_locked)
        """
        self.failed_attempts += 1
        remaining = max(0, self.max_attempts - self.failed_attempts)
        if self.failed_attempts >= self.max_attempts:
            self.locked_until = time.time() + self.lockout_seconds
            logger.warning("🚨 OTP verification locked out for %d seconds!", self.lockout_seconds)
            return 0, True
        return remaining, False

    def get_remaining_attempts(self) -> int:
        if self.is_locked():
            return 0
        return max(0, self.max_attempts - self.failed_attempts)

    def reset(self):
        """Resets failed attempts after a valid OTP verification."""
        self.failed_attempts = 0
        self.locked_until = 0.0


# Global singleton instance for the edge locker OTP station
otp_rate_limiter = OtpRateLimiter()
