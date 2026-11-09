"""
Contract & Edge Integration Tests.
Verifies that Edge functions and classes produce outputs compliant with shared contracts.
"""
import pytest
from contracts.schemas import (
    DepositAction,
    DepositStatus,
    LockerAuth,
    ScanResult,
    WeightMeasurement,
    SystemState,
)
from edge.cv.ocr_utils import extract_tracking_number, extract_weight_grams
from edge.cv.scanner import PackageScanner
from edge.hardware.hx711_loadcell import LoadCellController
from edge.hardware.lock_controller import LockController
from edge.hardware.indicators import IndicatorController
from edge.core.keypad import KeypadReader
from edge.core.fsm import LockerStateMachine, verify_deposit_integrity


def test_tracking_regex_parsers():
    # Test SPX tracking
    assert extract_tracking_number("SPX038472918VN") == "SPX038472918VN"
    assert extract_tracking_number("Text before SPXVN09812456 text after") == "SPXVN09812456"

    # Test GHN tracking
    assert extract_tracking_number("Don hang GHN78921820") == "GHN78921820"

    # Test empty or invalid
    assert extract_tracking_number("") is None
    assert extract_tracking_number("random plain text without codes") is None


def test_weight_regex_parsers():
    assert extract_weight_grams("Khoi luong: 450g") == 450.0
    assert extract_weight_grams("Weight: 1.2 kg") == 1200.0
    assert extract_weight_grams("Trọng lượng: 0.75kg") == 750.0
    assert extract_weight_grams("No weight specified") is None


def test_package_scanner_mock_contract():
    scanner = PackageScanner(mock_mode=True)
    res = scanner.scan_package_label(timeout=1.0)
    assert isinstance(res, ScanResult)
    assert res.tracking_number is not None
    assert res.confidence >= 0.0


def test_loadcell_controller_mock_contract():
    loadcell = LoadCellController(mock_mode=True)
    loadcell.tare(locker_id=1)
    measurement = loadcell.measure_weight_delta(locker_id=1, expected_weight=500.0)
    assert isinstance(measurement, WeightMeasurement)
    assert measurement.locker_id == 1
    assert measurement.current_weight_grams > 0.0


def test_lock_controller_mock_contract():
    lock = LockController(mock_mode=True)
    success = lock.open_locker_door(locker_id=1, duration_sec=0.1)
    assert success is True
    assert lock.is_door_closed(locker_id=1) is True


def test_keypad_rate_limiter_and_lockout():
    keypad = KeypadReader(mock_mode=True)
    assert keypad.is_locked_out() is False

    # Simulate 3 failed attempts
    keypad.record_failed_attempt()
    keypad.record_failed_attempt()
    keypad.record_failed_attempt()

    assert keypad.is_locked_out() is True
    assert keypad.get_remaining_lockout_seconds() > 0

    # Reset
    keypad.reset_attempts()
    assert keypad.is_locked_out() is False


def test_fsm_initial_state():
    fsm = LockerStateMachine()
    assert fsm.state == SystemState.IDLE
    fsm.reset_to_idle()
    assert fsm.state == SystemState.IDLE


def test_embedded_contracts_are_synchronized():
    scan = ScanResult(tracking_number="SPX123", weight_declared=500)
    assert scan.success is True
    assert scan.ocr_weight == 500

    measurement = WeightMeasurement(
        locker_id=1,
        current_weight_grams=510,
        delta_grams=510,
        is_stable=True,
    )
    assert measurement.after_weight == 510
    assert measurement.delta_weight == 510


def test_deposit_integrity_rejects_empty_and_accepts_valid_package():
    auth = LockerAuth(
        is_allowed=True,
        locker_id=1,
        expected_weight=500,
        weight_tolerance=20,
    )
    empty = verify_deposit_integrity(
        auth,
        WeightMeasurement(locker_id=1, delta_weight=5, is_stable=True),
    )
    assert empty.status == DepositStatus.EMPTY_DEPOSIT
    assert empty.action == DepositAction.TRIGGER_BUZZER_ALARM

    valid = verify_deposit_integrity(
        auth,
        WeightMeasurement(locker_id=1, delta_weight=510, is_stable=True),
    )
    assert valid.status == DepositStatus.SUCCESS
    assert valid.action == DepositAction.CONFIRM_SERVER_AND_LOCK


def test_keypad_event_contract_and_otp_validation():
    keypad = KeypadReader(mock_mode=True)
    event = keypad.listen_keypad_otp(mock_input="123456")
    assert event.entered_pin == "123456"
    assert event.is_rate_limited is False
