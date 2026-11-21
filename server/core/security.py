"""
Security, OTP Engine and Rate Limiter Module [Person 4].
Generates cryptographically random numeric OTPs and enforces rate limiting on verification attempts.
"""
import time
import hmac
import hashlib
import secrets
import string
import logging
from datetime import datetime, timedelta, timezone
from typing import Tuple, Optional

from server.core.config import settings

logger = logging.getLogger("server.core.security")


def hash_password(password: str) -> str:
    """Hashes a plaintext password with SHA-256 and application SECRET_KEY."""
    salted = f"{settings.SECRET_KEY}:{password}".encode("utf-8")
    return "sha256$" + hashlib.sha256(salted).hexdigest()


def verify_password(plain_password: str, stored_hash: Optional[str]) -> bool:
    """Verifies plaintext password against stored hash (also supports legacy plain defaults)."""
    if not stored_hash:
        return False
    if stored_hash.startswith("sha256$"):
        expected = hash_password(plain_password)
        return hmac.compare_digest(expected, stored_hash)
    return hmac.compare_digest(plain_password, stored_hash)


def create_session_token(user_id: int, role: str) -> str:
    """Generates an HMAC-signed lightweight session token for web clients."""
    issued_at = int(time.time())
    payload = f"{user_id}:{role}:{issued_at}"
    sig = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:24]
    return f"{payload}:{sig}"


def parse_session_token(token: str) -> Optional[Tuple[int, str]]:
    """Validates an HMAC-signed session token and returns (user_id, role) if valid."""
    try:
        parts = token.strip().split(":")
        if len(parts) != 4:
            return None
        user_id_str, role, issued_at, sig = parts
        payload = f"{user_id_str}:{role}:{issued_at}"
        expected_sig = hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()[:24]
        if not hmac.compare_digest(sig, expected_sig):
            return None
        return int(user_id_str), role
    except Exception:
        return None


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
