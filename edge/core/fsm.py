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
from edge.config import WEIGHT_TOLERANCE_GRAMS
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
) -> DepositDecision:
    """Apply the edge-side anti-empty and stability checks before confirmation."""
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

    expected = getattr(auth, "expected_weight", None)
    tolerance = getattr(auth, "weight_tolerance", WEIGHT_TOLERANCE_GRAMS)
    if expected and abs(measured - expected) > tolerance:
        return DepositDecision(
            status=DepositStatus.WEIGHT_MISMATCH,
            action=DepositAction.TRIGGER_BUZZER_ALARM,
            message=f"Weight mismatch: measured {measured:.1f}g, expected {expected:.1f}g.",
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
        order_id = auth.order_id or "unknown"
        logger.info("Package authorized for Locker %d", locker_id)

        # 3. Unlock locker door
        self.transition_to(SystemState.UNLOCKED_DEPOSIT)
        self.indicators.success_sound()
        self.indicators.display_message(f"Locker {locker_num} Open", "Insert Parcel")

        # Tare before parcel placement
        self.loadcell.tare(locker_num)
        self.lock.open_locker_door(locker_num)

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
            self.indicators.error_sound()
            self.indicators.display_message("Deposit Error", decision.message[:16])
            self.transition_to(SystemState.ERROR)
            time.sleep(2.0)
            self.transition_to(SystemState.IDLE)
            return False

        # 5. Confirm deposit to server
        self.transition_to(SystemState.DEPOSIT_CONFIRMED)
        confirm_res = self.api_client.confirm_deposit(
            order_id=order_id,
            locker_number=locker_num,
            delta_weight=measured_int,
        )

        if confirm_res.success:
            self.indicators.success_sound()
            self.indicators.display_message("Deposit Success!", f"Locker {locker_num} Locked")
            logger.info("Deposit successfully completed for order #%d. OTP: %s", order_id, confirm_res.otp_generated)
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

        if otp_res.valid and otp_res.locker_number is not None:
            self.keypad.reset_attempts()
            self.transition_to(SystemState.RETRIEVING)
            self.indicators.success_sound()
            self.indicators.display_message(f"Locker {otp_res.locker_number} Open", "Take Your Parcel")
            self.lock.open_locker_door(otp_res.locker_number)
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
