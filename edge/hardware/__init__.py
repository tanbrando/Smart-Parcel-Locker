"""Hardware Package [Person 2] - Ultrasonic Sensor, Servo Lock, LCD 1602, Buzzer."""
from edge.hardware.ultrasonic_sensor import (
    UltrasonicSensor,
    measure_distance_cm,
    calibrate_empty_baseline,
    is_locker_occupied,
)
from edge.hardware.servo_lock import (
    ServoLockController,
    unlock_door,
    lock_door,
    is_door_closed,
    get_lock_state,
    lock_if_occupied,
    open_locker_door,
)
from edge.hardware.indicators import IndicatorController
from edge.hardware.lock_controller import LockController

__all__ = [
    # Ultrasonic sensor
    "UltrasonicSensor",
    "measure_distance_cm",
    "calibrate_empty_baseline",
    "is_locker_occupied",
    # Servo lock & door
    "ServoLockController",
    "LockController",
    "unlock_door",
    "lock_door",
    "is_door_closed",
    "get_lock_state",
    "lock_if_occupied",
    "open_locker_door",
    # Indicators
    "IndicatorController",
]



