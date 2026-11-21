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


def test_four_lockers_supported():
    lock = ServoLockController(mock_mode=True)
    sensor = UltrasonicSensor(mock_mode=True, baseline_empty_cm=35.0, occupied_margin_cm=5.0)
    assert sorted(lock.servo_pins.keys()) == [1, 2, 3, 4]
    assert sorted(lock.door_switch_pins.keys()) == [1, 2, 3, 4]
    assert sorted(sensor.trig_pins.keys()) == [1, 2, 3, 4]
    assert sorted(sensor.echo_pins.keys()) == [1, 2, 3, 4]

    # Verify locker 4 works end-to-end
    assert lock.unlock_door(4) is True
    assert lock.get_lock_state(4) == LockState.UNLOCKED
    assert lock.lock_door(4) is True
    assert lock.get_lock_state(4) == LockState.LOCKED
    sensor.set_mock_distance(15.0, locker_id=4)
    assert sensor.is_locker_occupied(locker_id=4).occupied is True


def test_no_gpio_pin_conflicts():
    """Ensures Raspberry Pi 4B GPIO pinout has zero conflicts across all peripherals."""
    from edge.config import validate_gpio_pinout

    conflicts = validate_gpio_pinout()
    assert conflicts == [], f"GPIO pin conflicts detected: {conflicts}"


def test_fsm_sends_ultrasonic_distance_to_server():
    """Ensures FSM passes real HC-SR04 distance_cm and empty_distance_cm to confirm_deposit."""
    from unittest.mock import MagicMock, patch
    from contracts.schemas import DepositConfirmationResponse, LockerAuth, OrderStatus
    from edge.core.api_client import EdgeApiClient
    from edge.core.fsm import LockerStateMachine

    sensor = UltrasonicSensor(mock_mode=True, baseline_empty_cm=35.0, occupied_margin_cm=5.0)
    sensor.set_mock_distance(13.5, locker_id=2)
    lock = ServoLockController(mock_mode=True)
    lock.set_mock_door_closed(True, locker_id=2)

    mock_api = MagicMock(spec=EdgeApiClient)
    mock_api.request_door_unlock.return_value = LockerAuth(is_allowed=True, locker_id=2, order_id=99)
    mock_api.confirm_deposit.return_value = DepositConfirmationResponse(
        success=True,
        status=OrderStatus.STORED,
        otp_generated="123456",
        distance_cm=13.5,
        parcel_detected=True,
    )

    fsm = LockerStateMachine(ultrasonic=sensor, lock=lock, api_client=mock_api)
    with patch("time.sleep", return_value=None):
        assert fsm.handle_courier_deposit() is True

    mock_api.confirm_deposit.assert_called_once_with(
        order_id=99,
        locker_number=2,
        delta_weight=0,
        distance_cm=13.5,
        empty_distance_cm=35.0,
    )


def test_keypad_preserves_initial_digit():
    """Ensures pressing the first OTP digit from IDLE does not drop that digit."""
    from edge.core.keypad import KeypadReader

    keypad = KeypadReader(mock_mode=True)
    assert keypad.get_pin_input(initial_digits="5") == "5"
    assert keypad.get_pin_input(mock_input="582194", initial_digits="5") == "582194"


def test_partial_hardware_mode_ultrasonic_disabled_and_active_lockers():
    """Verifies ENABLE_ULTRASONIC=false simulates occupied (14cm) and active_lockers filters servos."""
    sensor = UltrasonicSensor(mock_mode=False, baseline_empty_cm=35.0, occupied_margin_cm=5.0, enabled=False)
    occ = sensor.is_locker_occupied(locker_id=3)
    assert occ.occupied is True
    assert occ.distance_cm == 14.0
    assert occ.error is None

    lock = ServoLockController(mock_mode=True, active_lockers=[3, 4])
    assert lock.active_lockers == [3, 4]
    assert lock.unlock_door(3) is True
    assert lock.lock_door(4) is True




if __name__ == "__main__":
    tests = [
        test_ultrasonic_mock_distance_and_filtering,
        test_ultrasonic_occupancy_decision,
        test_ultrasonic_baseline_calibration,
        test_servo_lock_state_transitions,
        test_lock_if_occupied_logic,
        test_module_level_convenience_functions,
        test_four_lockers_supported,
    ]
    print(f"Running {len(tests)} Ultrasonic & Servo Hardware tests...\n")
    for t in tests:
        t()
        print(f"  [PASS] {t.__name__}")
    print("\nAll Ultrasonic & Servo tests passed successfully!")
