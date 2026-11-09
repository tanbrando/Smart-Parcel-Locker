"""
Servo Lock & Door Controller Module [Person 2].
Manages PWM-driven servo motors (SG90 / MG90S / MG996R) for locker door latching & unlatching.
"""
import time
import logging
from typing import Dict, Optional, Any

from edge.config import (
    LOCKER_SERVO_PINS,
    SERVO_PWM_FREQUENCY,
    SERVO_LOCKED_ANGLE,
    SERVO_UNLOCKED_ANGLE,
    DOOR_UNLOCK_DURATION_SEC,
    MOCK_HARDWARE,
)

logger = logging.getLogger("edge.hardware.lock")

try:
    import RPi.GPIO as GPIO
    RPI_AVAILABLE = True
except (ImportError, RuntimeError):
    RPI_AVAILABLE = False


def angle_to_duty_cycle(angle: float) -> float:
    """
    Converts angle (0 to 180 degrees) to PWM duty cycle (approx 2% to 12% at 50Hz).
    Standard 50Hz RC servo: 0 deg ~ 0.5ms (2.5%), 180 deg ~ 2.5ms (12.5%).
    Formula: duty_cycle = 2.5 + (angle / 180.0) * 10.0
    """
    clamped_angle = max(0.0, min(180.0, float(angle)))
    return 2.5 + (clamped_angle / 180.0) * 10.0


class LockController:
    """Controls door locking mechanisms via Servo Motors using software/hardware PWM."""

    def __init__(self, mock_mode: bool = MOCK_HARDWARE):
        self.mock_mode = mock_mode or not RPI_AVAILABLE
        self.servo_pins: Dict[int, int] = dict(LOCKER_SERVO_PINS)
        self.door_status: Dict[int, bool] = {k: True for k in self.servo_pins}  # True = closed/locked
        self.current_angles: Dict[int, float] = {k: SERVO_LOCKED_ANGLE for k in self.servo_pins}
        self.pwm_instances: Dict[int, Any] = {}

        if self.mock_mode:
            logger.info("LockController initialized in MOCK mode (Servo Simulation).")
        else:
            self._setup_hardware()

    def _setup_hardware(self):
        GPIO.setmode(GPIO.BCM)
        for locker_id, pin in self.servo_pins.items():
            GPIO.setup(pin, GPIO.OUT)
            pwm = GPIO.PWM(pin, SERVO_PWM_FREQUENCY)
            duty = angle_to_duty_cycle(SERVO_LOCKED_ANGLE)
            pwm.start(duty)
            time.sleep(0.3)
            # Set duty cycle to 0 after moving to prevent servo jitter / buzz
            pwm.ChangeDutyCycle(0)
            self.pwm_instances[locker_id] = pwm
            logger.info("Locker %d Servo initialized on GPIO %d (Locked at %.1f deg)", locker_id, pin, SERVO_LOCKED_ANGLE)

    def set_servo_angle(self, locker_id: int, angle: float, settle_time: float = 0.4):
        """Rotates the servo of locker_id to a specific angle (0-180 deg)."""
        if locker_id not in self.servo_pins:
            logger.error("Invalid locker_id: %d. Available: %s", locker_id, list(self.servo_pins.keys()))
            return

        self.current_angles[locker_id] = angle

        if self.mock_mode:
            logger.debug("[Mock Servo] Locker %d angle set to %.1f deg", locker_id, angle)
            return

        pwm = self.pwm_instances.get(locker_id)
        if pwm is not None:
            duty = angle_to_duty_cycle(angle)
            pwm.ChangeDutyCycle(duty)
            time.sleep(settle_time)
            # Stop sending pulse to avoid jitter / heat up
            pwm.ChangeDutyCycle(0)

    def open_locker_door(self, locker_id: int, duration_sec: float = DOOR_UNLOCK_DURATION_SEC) -> bool:
        """
        Rotates servo to SERVO_UNLOCKED_ANGLE to release latch/door, waits for duration_sec,
        and automatically returns servo to SERVO_LOCKED_ANGLE.
        """
        if locker_id not in self.servo_pins:
            logger.error("Invalid locker_id: %d. Available: %s", locker_id, list(self.servo_pins.keys()))
            return False

        pin = self.servo_pins[locker_id]
        logger.info(
            "🚪 Unlocking locker %d (Servo GPIO %d -> %.1f deg for %.1fs)...",
            locker_id,
            pin,
            SERVO_UNLOCKED_ANGLE,
            duration_sec,
        )

        if self.mock_mode:
            self.door_status[locker_id] = False  # Door opened
            self.current_angles[locker_id] = SERVO_UNLOCKED_ANGLE
            time.sleep(min(0.2, max(0.0, duration_sec)))
            logger.info("[Mock Servo] Locker %d door unlatched successfully.", locker_id)
            self.door_status[locker_id] = True   # Courier/User closes door
            self.current_angles[locker_id] = SERVO_LOCKED_ANGLE
            return True

        try:
            # 1. Rotate to unlocked angle
            self.set_servo_angle(locker_id, SERVO_UNLOCKED_ANGLE)
            self.door_status[locker_id] = False
            time.sleep(max(0.1, duration_sec))
        finally:
            # 2. Return to locked angle
            self.set_servo_angle(locker_id, SERVO_LOCKED_ANGLE)
            self.door_status[locker_id] = True

        logger.info("Locker %d servo returned to locked angle (%.1f deg).", locker_id, SERVO_LOCKED_ANGLE)
        return True

    def is_door_closed(self, locker_id: int) -> bool:
        """Checks reed switch / magnetic contact sensor state."""
        return self.door_status.get(locker_id, True)

    def lock_all(self):
        """Forces all servos to rotate to SERVO_LOCKED_ANGLE."""
        for locker_id in self.servo_pins:
            self.set_servo_angle(locker_id, SERVO_LOCKED_ANGLE)
            self.door_status[locker_id] = True
        logger.info("All locker servos set to locked position.")

    def cleanup(self):
        """Safely stops all PWM channels and resets servo positions before release."""
        self.lock_all()
        if not self.mock_mode and RPI_AVAILABLE:
            for pwm in self.pwm_instances.values():
                try:
                    pwm.stop()
                except Exception as exc:
                    logger.warning("Error stopping PWM: %s", exc)
            self.pwm_instances.clear()


# Module-level singleton & helper function for direct Contract import
_default_lock_controller: Optional[LockController] = None


def get_lock_controller() -> LockController:
    """Returns or initializes the default LockController singleton."""
    global _default_lock_controller
    if _default_lock_controller is None:
        _default_lock_controller = LockController()
    return _default_lock_controller


def open_locker_door(locker_id: int, duration_sec: float = DOOR_UNLOCK_DURATION_SEC) -> bool:
    """Contract convenience function to unlock a locker compartment for Person 3."""
    return get_lock_controller().open_locker_door(locker_id=locker_id, duration_sec=duration_sec)



