"""Servo-based locker door controller."""
import time
import logging
from typing import Dict

from edge.config import (
    LOCKER_SERVO_PINS,
    SERVO_PWM_FREQUENCY,
    SERVO_OPEN_ANGLE,
    SERVO_CLOSED_ANGLE,
    DOOR_UNLOCK_DURATION_SEC,
    MOCK_HARDWARE,
)

logger = logging.getLogger("edge.hardware.lock")

try:
    import RPi.GPIO as GPIO
    RPI_AVAILABLE = True
except (ImportError, RuntimeError):
    RPI_AVAILABLE = False


class LockController:
    """Controls locker latch servos and tracks door state."""

    def __init__(self, mock_mode: bool = MOCK_HARDWARE):
        self.mock_mode = mock_mode or not RPI_AVAILABLE
        self.servo_pins: Dict[int, int] = LOCKER_SERVO_PINS
        self.door_status: Dict[int, bool] = {k: True for k in self.servo_pins}
        self.pwm_channels: Dict[int, object] = {}

        if self.mock_mode:
            logger.info("LockController initialized in MOCK mode.")
        else:
            self._setup_hardware()

    def _setup_hardware(self):
        GPIO.setmode(GPIO.BCM)
        for locker_id, pin in self.servo_pins.items():
            GPIO.setup(pin, GPIO.OUT)
            pwm = GPIO.PWM(pin, SERVO_PWM_FREQUENCY)
            pwm.start(self._angle_to_duty_cycle(SERVO_CLOSED_ANGLE))
            self.pwm_channels[locker_id] = pwm
            logger.info("Locker %d servo initialized on GPIO %d", locker_id, pin)

    @staticmethod
    def _angle_to_duty_cycle(angle: float) -> float:
        """Convert a standard 0-180 degree servo angle to a PWM duty cycle."""
        angle = max(0.0, min(180.0, angle))
        return 2.5 + (angle / 18.0)

    def _set_servo_angle(self, locker_id: int, angle: float) -> None:
        if not self.mock_mode:
            self.pwm_channels[locker_id].ChangeDutyCycle(self._angle_to_duty_cycle(angle))

    def open_locker_door(self, locker_id: int, duration_sec: float = DOOR_UNLOCK_DURATION_SEC) -> bool:
        """
        Moves the latch servo to the open angle, then returns it to closed.
        """
        if locker_id not in self.servo_pins:
            logger.error("Invalid locker_id: %d. Available: %s", locker_id, list(self.servo_pins.keys()))
            return False

        pin = self.servo_pins[locker_id]
        logger.info("Opening locker %d (servo GPIO %d for %.1fs)...", locker_id, pin, duration_sec)

        if self.mock_mode:
            self.door_status[locker_id] = False
            time.sleep(duration_sec)
            self.door_status[locker_id] = True
            return True

        try:
            self._set_servo_angle(locker_id, SERVO_OPEN_ANGLE)
            self.door_status[locker_id] = False
            time.sleep(duration_sec)
        finally:
            self._set_servo_angle(locker_id, SERVO_CLOSED_ANGLE)
            self.door_status[locker_id] = True

        return True

    def is_door_closed(self, locker_id: int) -> bool:
        """Return the tracked door state (True means closed)."""
        return self.door_status.get(locker_id, True)

    def wait_for_door_closed(self, locker_id: int, timeout_sec: float = DOOR_UNLOCK_DURATION_SEC) -> bool:
        """Wait until a door is closed or the timeout expires."""
        deadline = time.monotonic() + timeout_sec
        while not self.is_door_closed(locker_id) and time.monotonic() < deadline:
            time.sleep(0.05)
        return self.is_door_closed(locker_id)

    def cleanup(self) -> None:
        """Stop servo PWM channels and release GPIO resources."""
        if self.mock_mode:
            return
        for pwm in self.pwm_channels.values():
            pwm.stop()
        GPIO.cleanup(list(self.servo_pins.values()))
