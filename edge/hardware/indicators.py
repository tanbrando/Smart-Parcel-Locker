"""
User Feedback Indicators Module [Person 2].
Controls LCD 1602 (I2C) display and Buzzer audible feedback.
"""
import time
import logging
from typing import Optional

from edge.config import (
    BUZZER_PIN,
    BUZZER_ACTIVE_HIGH,
    LCD_I2C_ADDR,
    LCD_I2C_BUS,
    LCD_COLS,
    LCD_ROWS,
    MOCK_HARDWARE,
)

logger = logging.getLogger("edge.hardware.indicators")

try:
    import RPi.GPIO as GPIO
    import smbus2
    HARDWARE_AVAILABLE = True
except (ImportError, RuntimeError):
    HARDWARE_AVAILABLE = False


class IndicatorController:
    """Combines LCD screen and Buzzer signals for immediate physical feedback."""

    def __init__(self, mock_mode: bool = MOCK_HARDWARE):
        self.mock_mode = mock_mode or not HARDWARE_AVAILABLE
        self._bus = None

        if self.mock_mode:
            logger.info("IndicatorController initialized in MOCK mode.")
        else:
            self._setup_hardware()

    def _setup_hardware(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(BUZZER_PIN, GPIO.OUT)
        GPIO.output(BUZZER_PIN, GPIO.LOW if BUZZER_ACTIVE_HIGH else GPIO.HIGH)
        try:
            self._bus = smbus2.SMBus(LCD_I2C_BUS)
            logger.info("LCD I2C bus %d connected at 0x%02X", LCD_I2C_BUS, LCD_I2C_ADDR)
        except Exception as exc:
            logger.warning("Could not open I2C bus for LCD (%s). Using console fallback.", exc)

    def beep(self, duration: float = 0.1, count: int = 1):
        """Emits short beep(s)."""
        logger.debug("Buzzer beep (duration=%.2fs, count=%d)", duration, count)
        if self.mock_mode or not HARDWARE_AVAILABLE:
            return

        high_val = GPIO.HIGH if BUZZER_ACTIVE_HIGH else GPIO.LOW
        low_val = GPIO.LOW if BUZZER_ACTIVE_HIGH else GPIO.HIGH

        for _ in range(count):
            GPIO.output(BUZZER_PIN, high_val)
            time.sleep(duration)
            GPIO.output(BUZZER_PIN, low_val)
            if count > 1:
                time.sleep(0.05)

    def success_sound(self):
        """Double beep for success."""
        self.beep(0.08, 2)

    def error_sound(self):
        """Long low beep for error or invalid entry."""
        self.beep(0.35, 1)

    def display_message(self, line1: str, line2: str = ""):
        """Displays 2 lines of text on the 16x2 LCD screen."""
        l1 = (line1[:LCD_COLS]).ljust(LCD_COLS)
        l2 = (line2[:LCD_COLS]).ljust(LCD_COLS)

        logger.info("[LCD Display] | %s | %s |", l1.strip(), l2.strip())

        if self.mock_mode or self._bus is None:
            return

        # Real I2C HD44780 LCD command writing would go here
        # (commands 0x80 for Line 1, 0xC0 for Line 2)

    def clear(self):
        """Clears LCD display screen."""
        self.display_message("", "")

