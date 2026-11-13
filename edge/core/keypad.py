"""
4x4 Matrix Keypad Reader Module [Person 3].
Features rate-limiting and lockout protection against brute-force attacks.
"""
import time
import logging
from typing import Optional, List

from edge.config import (
    KEYPAD_ROW_PINS,
    KEYPAD_COL_PINS,
    KEYPAD_MAX_ATTEMPTS,
    KEYPAD_LOCKOUT_SECONDS,
    MOCK_HARDWARE,
)
from contracts.schemas import KeypadEvent

logger = logging.getLogger("edge.core.keypad")

try:
    import RPi.GPIO as GPIO
    RPI_AVAILABLE = True
except (ImportError, RuntimeError):
    RPI_AVAILABLE = False


# Bố cục tùy chỉnh (1-9 nằm ở 9 ô đầu S1-S9, bỏ qua phím S10 bị hỏng):
# S1=1, S2=2, S3=3, S4=4 | S5=5, S6=6, S7=7, S8=8 | S9=9, S10=(hỏng), S11=0, S12=C | S13=*, S14=0, S15=#, S16=D
KEYPAD_MATRIX = [
    ["1", "2", "3", "4"],
    ["5", "6", "7", "8"],
    ["9", "",  "0", "C"],
    ["*", "0", "#", "D"],
]


class KeypadReader:
    """Scans 4x4 keypad matrix and enforces rate-limiting / lockouts."""

    def __init__(self, mock_mode: bool = MOCK_HARDWARE):
        self.mock_mode = mock_mode or not RPI_AVAILABLE
        self.failed_attempts: int = 0
        self.lockout_until: float = 0.0

        if self.mock_mode:
            logger.info("KeypadReader initialized in MOCK mode.")
        else:
            self._setup_hardware()

    def _setup_hardware(self):
        GPIO.setmode(GPIO.BCM)
        for row in KEYPAD_ROW_PINS:
            GPIO.setup(row, GPIO.OUT)
            GPIO.output(row, GPIO.LOW)

        for col in KEYPAD_COL_PINS:
            GPIO.setup(col, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

    def is_locked_out(self) -> bool:
        """Returns True if user is temporarily locked out due to failed attempts."""
        remaining = self.lockout_until - time.time()
        return remaining > 0

    def get_remaining_lockout_seconds(self) -> int:
        return max(0, int(self.lockout_until - time.time()))

    def record_failed_attempt(self):
        """Increments failed attempt counter and triggers lockout if threshold reached."""
        self.failed_attempts += 1
        logger.warning("Keypad failed attempt: %d / %d", self.failed_attempts, KEYPAD_MAX_ATTEMPTS)
        if self.failed_attempts >= KEYPAD_MAX_ATTEMPTS:
            self.lockout_until = time.time() + KEYPAD_LOCKOUT_SECONDS
            logger.error("🚨 Keypad locked out for %d seconds!", KEYPAD_LOCKOUT_SECONDS)

    def reset_attempts(self):
        """Resets failed attempt counter after successful entry."""
        self.failed_attempts = 0
        self.lockout_until = 0.0

    def scan_single_key(self) -> Optional[str]:
        """Scans the physical matrix for an active keypress."""
        if self.mock_mode:
            return None

        for r_idx, r_pin in enumerate(KEYPAD_ROW_PINS):
            GPIO.output(r_pin, GPIO.HIGH)
            for c_idx, c_pin in enumerate(KEYPAD_COL_PINS):
                if GPIO.input(c_pin) == GPIO.HIGH:
                    # Debounce
                    time.sleep(0.15)
                    GPIO.output(r_pin, GPIO.LOW)
                    return KEYPAD_MATRIX[r_idx][c_idx] or None
            GPIO.output(r_pin, GPIO.LOW)

        return None

    def get_pin_input(
        self,
        timeout: float = 30.0,
        max_digits: int = 6,
        mock_input: Optional[str] = None,
    ) -> Optional[str]:
        """
        Reads user input until '#' is pressed or `max_digits` is reached.
        Returns the entered string, or None on timeout/lockout.
        """
        if self.is_locked_out():
            logger.warning("Cannot accept input: Keypad is locked out.")
            return None

        if self.mock_mode:
            if mock_input:
                logger.info("[Mock Keypad] Received mock PIN input: %s", mock_input)
                return mock_input
            return "582194"

        buffer: List[str] = []
        start_time = time.time()

        while (time.time() - start_time) < timeout:
            if self.is_locked_out():
                return None

            key = self.scan_single_key()
            if key:
                if key == "#":  # Submit key
                    logger.info("[Keypad] Nhấn '#' xác nhận OTP.")
                    break
                elif key == "*":  # Backspace key
                    if buffer:
                        buffer.pop()
                        logger.info("[Keypad] Xóa 1 số (còn %d/%d số)", len(buffer), max_digits)
                elif key.isdigit():
                    buffer.append(key)
                    logger.info("[Keypad] Nhận phím '%s' (%d/%d)", key, len(buffer), max_digits)
                    if len(buffer) >= max_digits:
                        break

            time.sleep(0.05)

        if not buffer:
            return None

        return "".join(buffer)

    def listen_keypad_otp(
        self,
        timeout: float = 30.0,
        mock_input: Optional[str] = None,
    ) -> KeypadEvent:
        """Read one OTP attempt and return the complete keypad contract."""
        if self.is_locked_out():
            return KeypadEvent(
                attempts_count=self.failed_attempts,
                is_rate_limited=True,
                remaining_lock_time=self.get_remaining_lockout_seconds(),
            )

        entered_pin = self.get_pin_input(
            timeout=timeout,
            max_digits=6,
            mock_input=mock_input,
        ) or ""
        return KeypadEvent(
            entered_pin=entered_pin,
            attempts_count=self.failed_attempts,
            is_rate_limited=self.is_locked_out(),
            remaining_lock_time=self.get_remaining_lockout_seconds(),
        )
