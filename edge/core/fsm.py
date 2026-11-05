"""
Finite State Machine (FSM) Module [Person 3].
Orchestrates hardware drivers, computer vision, and cloud API into a cohesive locker lifecycle.
"""
import time
import logging
from typing import Optional

from contracts.schemas import SystemState
from edge.config import WEIGHT_TOLERANCE_GRAMS
from edge.cv.scanner import PackageScanner
from edge.hardware.hx711_loadcell import LoadCellController
from edge.hardware.lock_controller import LockController
from edge.hardware.indicators import IndicatorController
from edge.core.keypad import KeypadReader
from edge.core.api_client import EdgeApiClient

logger = logging.getLogger("edge.core.fsm")


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
        verify_res = self.api_client.verify_package(scan_res.tracking_number)

        if not verify_res.verified or verify_res.locker_id is None:
            self.indicators.error_sound()
            self.indicators.display_message("Rejected", verify_res.message[:16])
            self.transition_to(SystemState.ERROR)
            time.sleep(2.5)
            self.transition_to(SystemState.IDLE)
            return False

        locker_id = verify_res.locker_id
        order_id = verify_res.order_id or "unknown"
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

        expected_w = verify_res.declared_weight_grams
        measurement = self.loadcell.measure_weight_delta(locker_id, expected_weight=expected_w)

        # Weight validation check
        if expected_w is not None and expected_w > 0:
            tolerance = verify_res.tolerance_grams or WEIGHT_TOLERANCE_GRAMS
            diff = abs(measurement.current_weight_grams - expected_w)
            if diff > tolerance:
                logger.warning(
                    "Weight mismatch! Measured: %.1fg, Expected: %.1fg (+/- %.1fg)",
                    measurement.current_weight_grams,
                    expected_w,
                    tolerance,
                )
                self.indicators.error_sound()
                self.indicators.display_message("Weight Mismatch", f"{measurement.current_weight_grams}g vs {expected_w}g")
                # Depending on business rules, we could reject or accept with alert flag

        # 5. Confirm deposit to server
        self.transition_to(SystemState.DEPOSIT_CONFIRMED)
        confirm_res = self.api_client.confirm_deposit(
            order_id=order_id,
            locker_id=locker_id,
            tracking_number=scan_res.tracking_number,
            final_weight=measurement.current_weight_grams,
        )

        if confirm_res.success:
            self.indicators.success_sound()
            self.indicators.display_message("Deposit Success!", f"Locker {locker_id} Locked")
            logger.info("Deposit successfully completed for order %s", order_id)
        else:
            self.indicators.error_sound()
            self.indicators.display_message("Confirm Error", confirm_res.message[:16])

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
        otp_res = self.api_client.verify_otp(pin)

        if otp_res.success and otp_res.locker_id is not None:
            self.keypad.reset_attempts()
            self.transition_to(SystemState.RETRIEVING)
            self.indicators.success_sound()
            self.indicators.display_message(f"Locker {otp_res.locker_id} Open", "Take Your Parcel")
            self.lock.open_locker_door(otp_res.locker_id)
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

