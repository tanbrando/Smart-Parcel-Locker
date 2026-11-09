"""
Contract & Edge Integration Tests.
Verifies that Edge functions and classes produce outputs compliant with shared contracts.
"""
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
from edge.hardware.hx711_loadcell import LoadCellController, measure_weight_delta
from edge.hardware.lock_controller import LockController, open_locker_door
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
    assert measurement.delta_grams == measurement.current_weight_grams
    assert measurement.is_stable is True

    # Second reading with additional parcel weight should report accurate delta (ΔW)
    measurement_2 = loadcell.measure_weight_delta(locker_id=1, expected_weight=800.0)
    assert measurement_2.delta_grams == round(
        measurement_2.current_weight_grams - measurement.current_weight_grams, 2
    )


def test_loadcell_noise_filtering_algorithm():
    # 10 samples where 2 extreme spikes (-99999.0 and +999999.0) occur due to HX711 noise
    noisy_samples = [
        -99999.0,
        210000.0,
        210050.0,
        209980.0,
        210010.0,
        210020.0,
        209990.0,
        210000.0,
        210010.0,
        999999.0,
    ]
    filtered_mean, std_dev = LoadCellController.filter_samples(noisy_samples, trim_ratio=0.2)
    # Outlier spikes should be completely removed; mean should be ~210007.5 with very low std_dev
    assert 209950.0 <= filtered_mean <= 210060.0
    assert std_dev < 50.0


def test_lock_controller_mock_contract():
    lock = LockController(mock_mode=True)
    success = lock.open_locker_door(locker_id=1, duration_sec=0.05)
    assert success is True
    assert lock.is_door_closed(locker_id=1) is True
    assert lock.open_locker_door(locker_id=999, duration_sec=0.05) is False


def test_hardware_module_level_contract_functions():
    # Direct contract functions required by Person 2 -> Person 3 specification
    assert open_locker_door(locker_id=2, duration_sec=0.05) is True
    w_res = measure_weight_delta(locker_id=2, expected_weight=350.0)
    assert isinstance(w_res, WeightMeasurement)
    assert w_res.locker_id == 2


def test_indicator_controller_lcd_i2c_and_buzzer():
    written_bytes = []

    class DummyI2CBus:
        def write_byte(self, addr, val):
            written_bytes.append((addr, val))

    dummy_bus = DummyI2CBus()
    indicators = IndicatorController(mock_mode=True, i2c_bus=dummy_bus, lcd_addr=0x27)
    # Initialization should have sent HD44780 4-bit setup sequence
    assert len(written_bytes) > 0

    written_bytes.clear()
    indicators.display_message("Locker 1 Open", "Insert Parcel")
    assert indicators.last_displayed[0].startswith("Locker 1 Open")
    assert indicators.last_displayed[1].startswith("Insert Parcel")
    # Every character on 2 lines (32 chars) + 2 line address commands writes nibbles over I2C
    assert len(written_bytes) > 60

    indicators.success_sound()
    indicators.error_sound()
    indicators.alarm_sound(cycles=2)
    indicators.clear()
    assert indicators.last_displayed[0].strip() == ""


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
if __name__ == "__main__":
    test_functions = [
        test_tracking_regex_parsers,
        test_weight_regex_parsers,
        test_package_scanner_mock_contract,
        test_loadcell_controller_mock_contract,
        test_loadcell_noise_filtering_algorithm,
        test_lock_controller_mock_contract,
        test_hardware_module_level_contract_functions,
        test_indicator_controller_lcd_i2c_and_buzzer,
        test_keypad_rate_limiter_and_lockout,
        test_fsm_initial_state,
    ]
    print(f"Running {len(test_functions)} Edge Contract & Hardware tests...\n")
    for fn in test_functions:
        fn()
        print(f"  [PASS] {fn.__name__}")
    print("\nAll tests passed successfully!")



