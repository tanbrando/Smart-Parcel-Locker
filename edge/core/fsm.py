"""
Finite State Machine (FSM) Module [Person 3].
Orchestrates hardware drivers, computer vision, and cloud API into a cohesive locker lifecycle.
"""
import time
import logging
from typing import Optional

from contracts.schemas import (
    DepositAction,
    DepositDecision,
    DepositStatus,
    ScanResult,
    SystemState,
    WeightMeasurement,
)
from edge.config import WEIGHT_TOLERANCE_GRAMS, STRICT_WEIGHT_MATCH
from edge.cv.scanner import PackageScanner
from edge.hardware.hx711_loadcell import LoadCellController
from edge.hardware.lock_controller import LockController
from edge.hardware.indicators import IndicatorController
from edge.core.keypad import KeypadReader
from edge.core.api_client import EdgeApiClient

logger = logging.getLogger("edge.core.fsm")


def verify_deposit_integrity(
    auth,
    weight: WeightMeasurement,
    minimum_weight_grams: float = 20.0,
    strict_expected_match: bool = STRICT_WEIGHT_MATCH,
) -> DepositDecision:
    """Apply edge-side parcel weight validation (anti-empty, overload, and optional strict match)."""
    if not weight.is_stable:
        return DepositDecision(
            status=DepositStatus.UNSTABLE_WEIGHT,
            action=DepositAction.RETRY_MEASUREMENT,
            message="Weight reading is not stable.",
        )

    measured = weight.delta_weight or weight.delta_grams
    if measured < minimum_weight_grams:
        return DepositDecision(
            status=DepositStatus.EMPTY_DEPOSIT,
            action=DepositAction.TRIGGER_BUZZER_ALARM,
            message="No parcel was detected in the locker.",
        )

    max_allowed = getattr(auth, "max_allowed_weight", None)
    if max_allowed and measured > max_allowed:
        return DepositDecision(
            status=DepositStatus.WEIGHT_MISMATCH,
            action=DepositAction.TRIGGER_BUZZER_ALARM,
            message=f"Overweight: {measured:.1f}g exceeds locker max {max_allowed:.1f}g.",
        )

    expected = getattr(auth, "expected_weight", None)
    tolerance = getattr(auth, "weight_tolerance", WEIGHT_TOLERANCE_GRAMS)
    if expected and abs(measured - expected) > tolerance:
        if strict_expected_match:
            return DepositDecision(
                status=DepositStatus.WEIGHT_MISMATCH,
                action=DepositAction.TRIGGER_BUZZER_ALARM,
                message=f"Weight mismatch: measured {measured:.1f}g, expected {expected:.1f}g.",
            )
        logger.info(
            "Weight deviation accepted (strict match disabled): measured %.1fg vs expected %.1fg",
            measured,
            expected,
        )

    return DepositDecision(
        status=DepositStatus.SUCCESS,
        action=DepositAction.CONFIRM_SERVER_AND_LOCK,
        message="Parcel deposit verified successfully.",
    )


class LockerStateMachine:
    """Finite State Machine supervising the smart locker system."""

    def __init__(
        self,
        scanner: Optional[PackageScanner] = None,
        loadcell: Optional[LoadCellController] = None,
        lock: Optional[LockController] = None,
        indicators: Optional[IndicatorController] = None,
        keypad: Optional[KeypadReader] = None,
        api_client: Optional[EdgeApiClient] = None,
    ):
        self.state: SystemState = SystemState.IDLE
        self.scanner = scanner or PackageScanner()
        self.loadcell = loadcell or LoadCellController()
        self.lock = lock or LockController()
        self.indicators = indicators or IndicatorController()
        self.keypad = keypad or KeypadReader()
        self.api_client = api_client or EdgeApiClient()

        self._running = False
        logger.info("LockerStateMachine initialized in state %s", self.state)

    def transition_to(self, new_state: SystemState):
        logger.info("FSM Transition: %s -> %s", self.state.value, new_state.value)
        self.state = new_state

    def handle_courier_deposit(self) -> bool:
        """Executes full courier parcel drop-off workflow."""
        self.transition_to(SystemState.SCANNING)
        self.indicators.display_message("Courier Deposit", "Show barcode/QR")

        # 1. Scan parcel
        scan_res = self.scanner.scan_package_label()
        if not scan_res.tracking_number:
            self.indicators.error_sound()
            self.indicators.display_message("Scan Failed", "No barcode found")
            self.transition_to(SystemState.ERROR)
            time.sleep(2.0)
            self.transition_to(SystemState.IDLE)
            return False

        # 2. Verify with server
        self.transition_to(SystemState.VERIFYING)
        self.indicators.display_message("Verifying...", scan_res.tracking_number)
        auth = self.api_client.request_door_unlock(scan_res)

        if not auth.is_allowed or auth.locker_id is None:
            self.indicators.error_sound()
            self.indicators.display_message("Rejected", (auth.reject_reason or "Not authorized")[:16])
            self.transition_to(SystemState.ERROR)
            time.sleep(2.5)
            self.transition_to(SystemState.IDLE)
            return False

        locker_id = auth.locker_id
        order_id = auth.order_id or 0
        logger.info("Package authorized for Locker %d", locker_id)

        # 3. Unlock locker door
        self.transition_to(SystemState.UNLOCKED_DEPOSIT)
        self.indicators.success_sound()
        self.indicators.display_message(f"Locker {locker_id} Open", "Insert Parcel")

        # Tare before parcel placement
        self.loadcell.tare(locker_id)
        self.lock.open_locker_door(locker_id)

        # 4. Measure weight
        self.transition_to(SystemState.WEIGHING)
        self.indicators.display_message("Measuring weight", "Please wait...")

        expected_w = auth.expected_weight
        measurement = self.loadcell.measure_weight_delta(locker_id, expected_weight=expected_w)
        if not self.lock.wait_for_door_closed(locker_id):
            self.indicators.error_sound()
            self.indicators.display_message("Close Door", "Door not closed")
            self.transition_to(SystemState.ERROR)
            time.sleep(1.0)
            self.transition_to(SystemState.IDLE)
            return False

        decision = verify_deposit_integrity(auth, measurement)
        if decision.action != DepositAction.CONFIRM_SERVER_AND_LOCK:
            logger.warning("Deposit rejected by edge integrity check: %s", decision.message)
            if decision.action == DepositAction.TRIGGER_BUZZER_ALARM:
                self.indicators.alarm_sound()
            else:
                self.indicators.error_sound()
            self.indicators.display_message("Deposit Error", decision.message[:16])
            self.transition_to(SystemState.ERROR)
            time.sleep(2.0)
            self.transition_to(SystemState.IDLE)
            return False

        # 5. Confirm deposit to server
        measured_weight_val = measurement.delta_weight if measurement.delta_weight != 0.0 else measurement.delta_grams
        measured_int = int(round(measured_weight_val))
        order_id_int = int(order_id) if str(order_id).isdigit() else 0

        self.transition_to(SystemState.DEPOSIT_CONFIRMED)
        confirm_res = self.api_client.confirm_deposit(
            order_id=order_id_int,
            locker_number=locker_id,
            delta_weight=measured_int,
        )

        if confirm_res.success:
            self.indicators.success_sound()
            self.indicators.display_message("Deposit Success!", f"Lock{locker_id} OK: {measured_int}g")
            logger.info("Deposit successfully completed for order #%s. OTP: %s", order_id, confirm_res.otp_generated)
        else:
            self.indicators.error_sound()
            self.indicators.display_message("Confirm Error", "Deposit failed")

        time.sleep(2.5)
        self.transition_to(SystemState.IDLE)
        return confirm_res.success

    def handle_recipient_pickup(self, otp_input: Optional[str] = None) -> bool:
        """Executes recipient OTP collection workflow."""
        if self.keypad.is_locked_out():
            remain = self.keypad.get_remaining_lockout_seconds()
            self.indicators.error_sound()
            self.indicators.display_message("Locked Out", f"Wait {remain}s")
            return False

        self.transition_to(SystemState.KEYPAD_INPUT)
        self.indicators.display_message("Enter 6-digit OTP", "Press # to enter")

        pin = self.keypad.get_pin_input(timeout=20.0, mock_input=otp_input)
        if not pin:
            self.indicators.display_message("Timeout", "Returning to home")
            time.sleep(1.5)
            self.transition_to(SystemState.IDLE)
            return False

        # Verify OTP with server
        self.transition_to(SystemState.VERIFYING)
        self.indicators.display_message("Checking OTP...", pin)
        otp_res = self.api_client.handle_otp_submission(pin)

        target_locker = otp_res.locker_number or otp_res.locker_id
        if otp_res.valid and target_locker is not None:
            self.keypad.reset_attempts()
            self.transition_to(SystemState.RETRIEVING)
            self.indicators.success_sound()
            self.indicators.display_message(f"Locker {target_locker} Open", "Take Your Parcel")
            self.lock.open_locker_door(target_locker)
            time.sleep(2.0)
            self.transition_to(SystemState.IDLE)
            return True
        else:
            self.keypad.record_failed_attempt()
            self.indicators.error_sound()
            self.indicators.display_message("Invalid OTP", "Access Denied")
            self.transition_to(SystemState.ERROR)
            time.sleep(2.0)
            self.transition_to(SystemState.IDLE)
            return False

    def reset_to_idle(self):
        """Displays ready state."""
        self.transition_to(SystemState.IDLE)
        self.indicators.display_message("Smart Parcel Locker", "Press * (Drop)/# (Pick)")
