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



def wait_for_door_closed(locker_id: int, timeout_seconds: float = 60.0) -> bool:
    """Contract convenience function to wait for locker door closure."""
    return get_lock_controller().wait_for_door_closed(locker_id=locker_id, timeout_seconds=timeout_seconds)



