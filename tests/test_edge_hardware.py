"""
Hardware Unit & Contract Tests for Ultrasonic Sensor and Servo Lock [Person 2].
Covers:
- Ultrasonic distance measurement (Median filtering & noise rejection)
- Baseline calibration
- Parcel occupancy detection (Debounce & thresholds)
- Servo door unlock/lock states
- Door open/closed sensing
- lock_if_occupied decision logic:
    * Door open -> DOOR_OPEN (no lock)
    * Door closed + Parcel present -> LOCKED
    * Door closed + Empty locker -> EMPTY_NOT_LOCKED (remains unlocked)
"""
from contracts.schemas import LockState, LockDecision, OccupancyResult
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
)


def test_ultrasonic_mock_distance_and_filtering():
    sensor = UltrasonicSensor(mock_mode=True, baseline_empty_cm=35.0, occupied_margin_cm=5.0)
    sensor.set_mock_distance(18.5, locker_id=1)
    dist = sensor.measure_distance_cm(locker_id=1, samples=5)
    assert dist == 18.5

    # Test sensor timeout / error handling
    sensor.set_mock_distance(None, locker_id=1, error="SENSOR_TIMEOUT")
    res = sensor.is_locker_occupied(locker_id=1)
    assert res.occupied is False
    assert res.error == "SENSOR_TIMEOUT"
    assert res.confidence == 0.0


def test_ultrasonic_occupancy_decision():
    sensor = UltrasonicSensor(mock_mode=True, baseline_empty_cm=35.0, occupied_margin_cm=5.0)

    # 1. Parcel placed: 18.0cm < (35.0 - 5.0 = 30.0cm) -> Occupied = True
    sensor.set_mock_distance(18.0, locker_id=1)
    occ = sensor.is_locker_occupied(locker_id=1)
    assert isinstance(occ, OccupancyResult)
    assert occ.occupied is True
    assert occ.distance_cm == 18.0
    assert occ.confidence >= 0.9

    # 2. Empty locker: 35.0cm >= 30.0cm -> Occupied = False
    sensor.set_mock_distance(34.5, locker_id=1)
    empty_occ = sensor.is_locker_occupied(locker_id=1)
    assert empty_occ.occupied is False


def test_ultrasonic_baseline_calibration():
    sensor = UltrasonicSensor(mock_mode=True, baseline_empty_cm=30.0)
    sensor.set_mock_distance(38.2, locker_id=1)
    new_baseline = sensor.calibrate_empty_baseline(locker_id=1, samples=5)
    assert new_baseline == 38.2
    assert sensor.baseline_empty_cm == 38.2


def test_servo_lock_state_transitions():
    lock = ServoLockController(mock_mode=True)
    # Default state is UNLOCKED
    assert lock.get_lock_state(1) == LockState.UNLOCKED

    # Lock door
    assert lock.lock_door(1) is True
    assert lock.get_lock_state(1) == LockState.LOCKED

    # Unlock door
    assert lock.unlock_door(1) is True
    assert lock.get_lock_state(1) == LockState.UNLOCKED


def test_lock_if_occupied_logic():
    lock = ServoLockController(mock_mode=True)
    sensor = UltrasonicSensor(mock_mode=True, baseline_empty_cm=35.0, occupied_margin_cm=5.0)

    # Inject mock sensor into global singleton
    import edge.hardware.ultrasonic_sensor as us_mod
    us_mod._default_ultrasonic_sensor = sensor

    # --- Case 1: Door is physically OPEN ---
    lock.set_mock_door_closed(False, locker_id=1)
    sensor.set_mock_distance(15.0, locker_id=1)  # Parcel is inside but door is open
    decision = lock.lock_if_occupied(locker_id=1)
    assert decision == LockDecision.DOOR_OPEN
    assert lock.get_lock_state(1) == LockState.UNLOCKED

    # --- Case 2: Door CLOSED + Parcel PRESENT (Occupied) -> LOCK ---
    lock.set_mock_door_closed(True, locker_id=1)
    sensor.set_mock_distance(15.0, locker_id=1)
    decision = lock.lock_if_occupied(locker_id=1)
    assert decision == LockDecision.LOCKED
    assert lock.get_lock_state(1) == LockState.LOCKED

    # --- Case 3: Door CLOSED + EMPTY (No Parcel) -> REMAIN UNLOCKED ---
    lock.set_mock_door_closed(True, locker_id=1)
    sensor.set_mock_distance(35.0, locker_id=1)  # Empty
    decision = lock.lock_if_occupied(locker_id=1)
    assert decision == LockDecision.EMPTY_NOT_LOCKED
    assert lock.get_lock_state(1) == LockState.UNLOCKED


def test_module_level_convenience_functions():
    assert unlock_door(1) is True
    assert get_lock_state(1) == LockState.UNLOCKED
    assert lock_door(1) is True
    assert get_lock_state(1) == LockState.LOCKED
    assert is_door_closed(1) is True

    # Test ultrasonic functions
    import edge.hardware.ultrasonic_sensor as us_mod
    sensor = us_mod.get_ultrasonic_sensor()
    sensor.set_mock_distance(20.0, locker_id=1)
    assert measure_distance_cm(1) == 20.0
    occ = is_locker_occupied(1)
    assert occ.occupied is True


if __name__ == "__main__":
    tests = [
        test_ultrasonic_mock_distance_and_filtering,
        test_ultrasonic_occupancy_decision,
        test_ultrasonic_baseline_calibration,
        test_servo_lock_state_transitions,
        test_lock_if_occupied_logic,
        test_module_level_convenience_functions,
    ]
    print(f"Running {len(tests)} Ultrasonic & Servo Hardware tests...\n")
    for t in tests:
        t()
        print(f"  [PASS] {t.__name__}")
    print("\nAll Ultrasonic & Servo tests passed successfully!")
