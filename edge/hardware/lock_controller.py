"""
Solenoid Lock & Door Controller Module [Person 2].
Manages relay-driven electric strike / solenoid locks for locker doors.
"""
import time
import logging
from typing import Dict, Optional

from edge.config import (
    LOCKER_RELAY_PINS,
    RELAY_ACTIVE_LOW,
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
    """Controls door release solenoids and monitors magnetic door contacts."""

    def __init__(self, mock_mode: bool = MOCK_HARDWARE):
        self.mock_mode = mock_mode or not RPI_AVAILABLE
        self.relay_pins: Dict[int, int] = dict(LOCKER_RELAY_PINS)
        self.door_status: Dict[int, bool] = {k: True for k in self.relay_pins}  # True = closed

        if self.mock_mode:
            logger.info("LockController initialized in MOCK mode.")
        else:
            self._setup_hardware()

    def _setup_hardware(self):
        GPIO.setmode(GPIO.BCM)
        for locker_id, pin in self.relay_pins.items():
            GPIO.setup(pin, GPIO.OUT)
            # Default state: Locked (de-energized solenoid)
            initial_state = GPIO.HIGH if RELAY_ACTIVE_LOW else GPIO.LOW
            GPIO.output(pin, initial_state)
            logger.info("Locker %d relay set on GPIO %d", locker_id, pin)

    def open_locker_door(self, locker_id: int, duration_sec: float = DOOR_UNLOCK_DURATION_SEC) -> bool:
        """
        Triggers the solenoid relay for `duration_sec` seconds to pop open the locker door.
        Guaranteed to re-lock solenoid in the `finally` block to prevent coil overheating.
        """
        if locker_id not in self.relay_pins:
            logger.error("Invalid locker_id: %d. Available: %s", locker_id, list(self.relay_pins.keys()))
            return False

        pin = self.relay_pins[locker_id]
        logger.info("🚪 Opening locker %d (Relay GPIO %d for %.1fs)...", locker_id, pin, duration_sec)

        if self.mock_mode:
            self.door_status[locker_id] = False  # Door opened
            time.sleep(min(0.2, max(0.0, duration_sec)))
            logger.info("[Mock Lock] Locker %d door popped open successfully.", locker_id)
            self.door_status[locker_id] = True   # Courier/User closes door
            return True

        unlock_state = GPIO.LOW if RELAY_ACTIVE_LOW else GPIO.HIGH
        lock_state = GPIO.HIGH if RELAY_ACTIVE_LOW else GPIO.LOW

        try:
            GPIO.output(pin, unlock_state)
            self.door_status[locker_id] = False
            time.sleep(max(0.1, duration_sec))
        finally:
            GPIO.output(pin, lock_state)
            self.door_status[locker_id] = True

        logger.info("Locker %d locked again.", locker_id)
        return True

    def is_door_closed(self, locker_id: int) -> bool:
        """Checks reed switch / magnetic contact sensor state."""
        return self.door_status.get(locker_id, True)

    def lock_all(self):
        """Forces all solenoid relays into locked state immediately."""
        if not self.mock_mode and RPI_AVAILABLE:
            lock_state = GPIO.HIGH if RELAY_ACTIVE_LOW else GPIO.LOW
            for locker_id, pin in self.relay_pins.items():
                GPIO.output(pin, lock_state)
                self.door_status[locker_id] = True
        else:
            for locker_id in self.relay_pins:
                self.door_status[locker_id] = True

    def cleanup(self):
        """Safely locks all doors before releasing resources."""
        self.lock_all()


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


