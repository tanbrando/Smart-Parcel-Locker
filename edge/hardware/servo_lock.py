"""
Servo Lock & Door Latch Controller Module [Person 2].
Controls PWM Servo motors (SG90 / MG996R) and Door Reed Switch / Limit Switch sensor.
Features intelligent locking:
- Empty locker: remains UNLOCKED.
- When parcel is deposited AND door is CLOSED: locks automatically.
- Anti-jitter PWM detachment, full mock mode, and status reporting.
"""
import time
import logging
from typing import Dict, Optional, Any

from contracts.schemas import LockState, LockDecision
from edge.config import (
    LOCKER_SERVO_PINS,
    SERVO_PWM_FREQUENCY,
    SERVO_LOCKED_ANGLE,
    SERVO_UNLOCKED_ANGLE,
    DOOR_SWITCH_PINS,
    DOOR_SWITCH_CLOSED_ACTIVE_LOW,
    MOCK_HARDWARE,
)
from edge.hardware.ultrasonic_sensor import get_ultrasonic_sensor

logger = logging.getLogger("edge.hardware.servo_lock")

try:
    import RPi.GPIO as GPIO
    RPI_AVAILABLE = True
except (ImportError, RuntimeError):
    RPI_AVAILABLE = False


def angle_to_duty_cycle(angle: float) -> float:
    """
    Converts angle (0 to 180 degrees) to PWM duty cycle (approx 2.5% to 12.5% at 50Hz).
    Formula: duty_cycle = 2.5 + (angle / 180.0) * 10.0
    """
    clamped_angle = max(0.0, min(180.0, float(angle)))
    return 2.5 + (clamped_angle / 180.0) * 10.0


class ServoLockController:
    """Controls door locking mechanisms via Servo Motors and checks door contact switches."""

    def __init__(self, mock_mode: bool = MOCK_HARDWARE):
        self.mock_mode = mock_mode or not RPI_AVAILABLE
        self.servo_pins: Dict[int, int] = dict(LOCKER_SERVO_PINS)
        self.door_switch_pins: Dict[int, int] = dict(DOOR_SWITCH_PINS)

        # Default state: Empty lockers are UNLOCKED (per business requirements in TASK)
        self.lock_states: Dict[int, LockState] = {k: LockState.UNLOCKED for k in self.servo_pins}
        self.current_angles: Dict[int, float] = {k: SERVO_UNLOCKED_ANGLE for k in self.servo_pins}

        # Door physical sensor state: True = Closed, False = Open
        # In mock mode, defaults to True (closed)
        self._mock_door_closed: Dict[int, bool] = {k: True for k in self.servo_pins}
        self.pwm_instances: Dict[int, Any] = {}

        if self.mock_mode:
            logger.info("ServoLockController initialized in MOCK mode (Unlocked by default).")
        else:
            self._setup_hardware()

    def _setup_hardware(self):
        GPIO.setmode(GPIO.BCM)
        # 1. Setup Servos
        for locker_id, pin in self.servo_pins.items():
            GPIO.setup(pin, GPIO.OUT)
            pwm = GPIO.PWM(pin, SERVO_PWM_FREQUENCY)
            duty = angle_to_duty_cycle(SERVO_UNLOCKED_ANGLE)
            pwm.start(duty)
            time.sleep(0.3)
            # Detach PWM signal to prevent servo jitter & heat up
            pwm.ChangeDutyCycle(0)
            self.pwm_instances[locker_id] = pwm
            logger.info("Locker %d Servo initialized on GPIO %d (UNLOCKED at %.1f deg)", locker_id, pin, SERVO_UNLOCKED_ANGLE)

        # 2. Setup Door Reed/Limit Switches (Internal Pull-Up enabled)
        for locker_id, pin in self.door_switch_pins.items():
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            logger.info("Locker %d Door switch initialized on GPIO %d (PUD_UP)", locker_id, pin)

    def set_mock_door_closed(self, closed: bool, locker_id: int = 1):
        """Allows tests to simulate door physically open or closed."""
        self._mock_door_closed[locker_id] = closed

    def is_door_closed(self, locker_id: int = 1) -> bool:
        """
        Reads physical reed switch / limit switch state.
        Returns True if door is physically shut/closed, False if open.
        """
        if self.mock_mode:
            return self._mock_door_closed.get(locker_id, True)

        pin = self.door_switch_pins.get(locker_id)
        if pin is None:
            logger.warning("No door switch pin configured for locker %d, defaulting to True", locker_id)
            return True

        val = GPIO.input(pin)
        # If active low (grounded when closed): 0 = Closed, 1 = Open
        if DOOR_SWITCH_CLOSED_ACTIVE_LOW:
            return val == 0
        return val == 1

    def _rotate_servo(self, locker_id: int, angle: float, settle_time: float = 0.4):
        """Rotates servo to target angle and detaches PWM pulse to prevent jitter."""
        if locker_id not in self.servo_pins:
            logger.error("Invalid locker_id: %d", locker_id)
            return

        self.current_angles[locker_id] = angle

        if self.mock_mode:
            logger.debug("[Mock Servo] Locker %d angle rotated to %.1f deg", locker_id, angle)
            return

        pwm = self.pwm_instances.get(locker_id)
        if pwm is not None:
            duty = angle_to_duty_cycle(angle)
            pwm.ChangeDutyCycle(duty)
            time.sleep(settle_time)
            # Detach PWM to avoid jitter
            pwm.ChangeDutyCycle(0)

    def unlock_door(self, locker_id: int = 1) -> bool:
        """
        Rotates servo to SERVO_UNLOCKED_ANGLE (e.g. 90 deg) allowing door to be opened.
        Returns True on success.
        """
        logger.info("🔓 Unlocking locker %d (Servo -> %.1f deg)...", locker_id, SERVO_UNLOCKED_ANGLE)
        self._rotate_servo(locker_id, SERVO_UNLOCKED_ANGLE)
        self.lock_states[locker_id] = LockState.UNLOCKED
        return True

    def lock_door(self, locker_id: int = 1) -> bool:
        """
        Rotates servo to SERVO_LOCKED_ANGLE (e.g. 0 deg) to secure the latch.
        Returns True on success.
        """
        logger.info("🔒 Locking locker %d (Servo -> %.1f deg)...", locker_id, SERVO_LOCKED_ANGLE)
        self._rotate_servo(locker_id, SERVO_LOCKED_ANGLE)
        self.lock_states[locker_id] = LockState.LOCKED
        return True

    def get_lock_state(self, locker_id: int = 1) -> LockState:
        """Returns the current state (LOCKED | UNLOCKED) for locker_id."""
        return self.lock_states.get(locker_id, LockState.UNLOCKED)

    def lock_if_occupied(self, locker_id: int = 1) -> LockDecision:
        """
        Evaluates door state and ultrasonic occupancy to make locking decision:
        1. If door is still open: DOES NOT LOCK -> returns LockDecision.DOOR_OPEN
        2. If door is closed AND parcel is detected: LOCKS -> returns LockDecision.LOCKED
        3. If door is closed BUT empty (no parcel): REMAINS UNLOCKED -> returns LockDecision.EMPTY_NOT_LOCKED
        """
        # Step 1: Check if door is closed
        if not self.is_door_closed(locker_id):
            logger.warning("Locker %d cannot be locked: Door is still OPEN.", locker_id)
            return LockDecision.DOOR_OPEN

        # Step 2: Check if parcel is inside locker
        ultrasonic = get_ultrasonic_sensor()
        occ = ultrasonic.is_locker_occupied(locker_id)

        if occ.occupied:
            logger.info("Locker %d has parcel (dist=%.2f cm) and door is CLOSED -> Locking!", locker_id, occ.distance_cm or 0.0)
            self.lock_door(locker_id)
            return LockDecision.LOCKED
        else:
            logger.warning("Locker %d door closed but EMPTY (dist=%.2f cm) -> Remaining UNLOCKED.", locker_id, occ.distance_cm or 0.0)
            self.unlock_door(locker_id)
            return LockDecision.EMPTY_NOT_LOCKED

    def cleanup(self):
        """Safely stops PWM channels."""
        if not self.mock_mode and RPI_AVAILABLE:
            for pwm in self.pwm_instances.values():
                try:
                    pwm.stop()
                except Exception as exc:
                    logger.warning("Error stopping PWM: %s", exc)
            self.pwm_instances.clear()

    # Backward compatibility method for earlier FSM & tests
    def open_locker_door(self, locker_id: int = 1, duration_sec: float = 4.0) -> bool:
        """Backward compatibility helper for FSM."""
        if locker_id not in self.servo_pins:
            logger.error("Invalid locker_id: %d. Available: %s", locker_id, list(self.servo_pins.keys()))
            return False
        return self.unlock_door(locker_id=locker_id)



# Singleton & convenience functions
_default_servo_lock: Optional[ServoLockController] = None


def get_servo_lock() -> ServoLockController:
    """Returns or initializes default ServoLockController singleton."""
    global _default_servo_lock
    if _default_servo_lock is None:
        _default_servo_lock = ServoLockController()
    return _default_servo_lock


def unlock_door(locker_id: int = 1) -> bool:
    """Unlocks locker door."""
    return get_servo_lock().unlock_door(locker_id=locker_id)


def lock_door(locker_id: int = 1) -> bool:
    """Locks locker door."""
    return get_servo_lock().lock_door(locker_id=locker_id)


def is_door_closed(locker_id: int = 1) -> bool:
    """Checks whether locker door is closed."""
    return get_servo_lock().is_door_closed(locker_id=locker_id)


def get_lock_state(locker_id: int = 1) -> LockState:
    """Returns current lock state (LOCKED | UNLOCKED)."""
    return get_servo_lock().get_lock_state(locker_id=locker_id)


def lock_if_occupied(locker_id: int = 1) -> LockDecision:
    """Evaluates door status and presence of parcel to intelligently lock or stay unlocked."""
    return get_servo_lock().lock_if_occupied(locker_id=locker_id)


# Backward-compatible alias for existing FSM code
def open_locker_door(locker_id: int = 1, duration_sec: float = 4.0) -> bool:
    """Backward compatibility helper for FSM."""
    return unlock_door(locker_id=locker_id)
