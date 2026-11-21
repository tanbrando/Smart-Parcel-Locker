"""
Lock Controller Module [Person 2].
Maintains backward compatibility by wrapping the modern ServoLockController.
"""
from edge.hardware.servo_lock import (
    ServoLockController,
    get_servo_lock,
    unlock_door,
    lock_door,
    is_door_closed,
    get_lock_state,
    lock_if_occupied,
    open_locker_door,
)

# Alias LockController to ServoLockController
LockController = ServoLockController
get_lock_controller = get_servo_lock

__all__ = [
    "LockController",
    "ServoLockController",
    "get_lock_controller",
    "get_servo_lock",
    "unlock_door",
    "lock_door",
    "is_door_closed",
    "get_lock_state",
    "lock_if_occupied",
    "open_locker_door",
]




