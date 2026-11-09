"""
User Feedback Indicators Module [Person 2].
Controls LCD 1602 (I2C via PCF8574 backpack) display and Buzzer audible feedback.
"""
import time
import logging
from typing import Any, Optional

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
    RPI_GPIO_AVAILABLE = True
except (ImportError, RuntimeError):
    RPI_GPIO_AVAILABLE = False

try:
    import smbus2
    SMBUS_AVAILABLE = True
except (ImportError, RuntimeError):
    SMBUS_AVAILABLE = False

HARDWARE_AVAILABLE = RPI_GPIO_AVAILABLE and SMBUS_AVAILABLE

# HD44780 I2C PCF8574 Control Constants
LCD_CHR: int = 1          # Mode - Sending data (character)
LCD_CMD: int = 0          # Mode - Sending command
LCD_LINE_1: int = 0x80    # LCD RAM address for the 1st line
LCD_LINE_2: int = 0xC0    # LCD RAM address for the 2nd line
LCD_BACKLIGHT: int = 0x08 # Backlight ON mask (0x00 = OFF)
LCD_ENABLE: int = 0x04    # Enable bit mask
E_PULSE_SEC: float = 0.0005
E_DELAY_SEC: float = 0.0005


class IndicatorController:
    """Combines LCD 1602 I2C screen and Buzzer signals for immediate physical feedback."""

    def __init__(
        self,
        mock_mode: bool = MOCK_HARDWARE,
        i2c_bus: Optional[Any] = None,
        lcd_addr: int = LCD_I2C_ADDR,
    ):
        self.mock_mode = mock_mode or not HARDWARE_AVAILABLE
        self.lcd_addr = lcd_addr
        self.backlight_mask: int = LCD_BACKLIGHT
        self._bus: Optional[Any] = i2c_bus
        self.last_displayed: tuple[str, str] = ("", "")

        if self.mock_mode and self._bus is None:
            logger.info("IndicatorController initialized in MOCK mode.")
        else:
            self._setup_hardware()

    def _setup_hardware(self):
        if RPI_GPIO_AVAILABLE and not self.mock_mode:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(BUZZER_PIN, GPIO.OUT)
            GPIO.output(BUZZER_PIN, GPIO.LOW if BUZZER_ACTIVE_HIGH else GPIO.HIGH)

        if self._bus is None and SMBUS_AVAILABLE and not self.mock_mode:
            try:
                self._bus = smbus2.SMBus(LCD_I2C_BUS)
                logger.info("LCD I2C bus %d connected at 0x%02X", LCD_I2C_BUS, self.lcd_addr)
            except Exception as exc:
                logger.warning("Could not open I2C bus for LCD (%s). Using console fallback.", exc)
                self._bus = None

        if self._bus is not None:
            try:
                self._init_lcd()
            except Exception as exc:
                logger.warning("LCD I2C initialization failed (%s). Disabling I2C writes.", exc)
                self._bus = None

    def _init_lcd(self):
        """Initializes HD44780 controller in 4-bit mode via I2C PCF8574 expander."""
        self._write_byte(0x33, LCD_CMD)  # 110011 Initialize
        self._write_byte(0x32, LCD_CMD)  # 110010 Initialize in 4-bit mode
        self._write_byte(0x06, LCD_CMD)  # 000110 Cursor move direction (increment)
        self._write_byte(0x0C, LCD_CMD)  # 001100 Display On, Cursor Off, Blink Off
        self._write_byte(0x28, LCD_CMD)  # 101000 Data length 4-bit, 2 lines, 5x8 font
        self._write_byte(0x01, LCD_CMD)  # 000001 Clear display
        time.sleep(0.002)

    def _write_byte(self, bits: int, mode: int):
        """Sends a byte to the LCD data/command register as two 4-bit nibbles."""
        if self._bus is None:
            return

        bits_high = mode | (bits & 0xF0) | self.backlight_mask
        bits_low = mode | ((bits << 4) & 0xF0) | self.backlight_mask

        # High nibble
        self._bus.write_byte(self.lcd_addr, bits_high)
        self._toggle_enable(bits_high)

        # Low nibble
        self._bus.write_byte(self.lcd_addr, bits_low)
        self._toggle_enable(bits_low)

    def _toggle_enable(self, bits: int):
        """Pulses the Enable pin on PCF8574 to latch nibble into HD44780."""
        if self._bus is None:
            return
        time.sleep(E_DELAY_SEC)
        self._bus.write_byte(self.lcd_addr, bits | LCD_ENABLE)
        time.sleep(E_PULSE_SEC)
        self._bus.write_byte(self.lcd_addr, bits & ~LCD_ENABLE)
        time.sleep(E_DELAY_SEC)

    def beep(self, duration: float = 0.1, count: int = 1, pause: float = 0.05):
        """Emits short beep(s) via active/passive buzzer GPIO."""
        logger.debug("Buzzer beep (duration=%.2fs, count=%d)", duration, count)
        if self.mock_mode or not RPI_GPIO_AVAILABLE:
            return

        high_val = GPIO.HIGH if BUZZER_ACTIVE_HIGH else GPIO.LOW
        low_val = GPIO.LOW if BUZZER_ACTIVE_HIGH else GPIO.HIGH

        for i in range(max(1, count)):
            GPIO.output(BUZZER_PIN, high_val)
            time.sleep(max(0.0, duration))
            GPIO.output(BUZZER_PIN, low_val)
            if i < count - 1 and pause > 0:
                time.sleep(pause)

    def success_sound(self):
        """Double short beep for successful scan/unlock/deposit."""
        self.beep(duration=0.08, count=2, pause=0.05)

    def error_sound(self):
        """Long beep for error or invalid OTP entry."""
        self.beep(duration=0.35, count=1)

    def alarm_sound(self, cycles: int = 6):
        """Rapid siren pattern for tamper/weight-fraud alert."""
        logger.warning("Buzzer ALARM triggered (%d cycles)!", cycles)
        self.beep(duration=0.12, count=cycles, pause=0.06)

    def display_message(self, line1: str, line2: str = ""):
        """Displays 2 lines of text on the 16x2 LCD screen."""
        l1 = (line1[:LCD_COLS]).ljust(LCD_COLS)
        l2 = (line2[:LCD_COLS]).ljust(LCD_COLS)
        self.last_displayed = (l1, l2)

        logger.info("[LCD Display] | %s | %s |", l1.strip(), l2.strip())

        if self._bus is None:
            return

        try:
            self._write_byte(LCD_LINE_1, LCD_CMD)
            for ch in l1:
                self._write_byte(ord(ch), LCD_CHR)

            if LCD_ROWS >= 2:
                self._write_byte(LCD_LINE_2, LCD_CMD)
                for ch in l2:
                    self._write_byte(ord(ch), LCD_CHR)
        except Exception as exc:
            logger.error("Failed writing to LCD over I2C: %s", exc)

    def set_backlight(self, enabled: bool = True):
        """Turns the LCD backlight on or off."""
        self.backlight_mask = LCD_BACKLIGHT if enabled else 0x00
        if self._bus is not None:
            try:
                self._bus.write_byte(self.lcd_addr, self.backlight_mask)
            except Exception as exc:
                logger.error("Failed setting LCD backlight: %s", exc)

    def clear(self):
        """Clears the LCD display screen."""
        self.last_displayed = (" " * LCD_COLS, " " * LCD_COLS)
        logger.info("[LCD Display] | <CLEARED> |")
        if self._bus is not None:
            try:
                self._write_byte(0x01, LCD_CMD)
                time.sleep(0.002)
            except Exception as exc:
                logger.error("Failed clearing LCD over I2C: %s", exc)

    def cleanup(self):
        """Safely turns off buzzer and clears LCD before shutdown."""
        if not self.mock_mode and RPI_GPIO_AVAILABLE:
            GPIO.output(BUZZER_PIN, GPIO.LOW if BUZZER_ACTIVE_HIGH else GPIO.HIGH)
        self.clear()


