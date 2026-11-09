"""
Finite State Machine (FSM) Module [Person 3].
Orchestrates hardware drivers, computer vision, and cloud API into a cohesive locker lifecycle.
"""
import time
import logging
from typing import Optional

from contracts.schemas import SystemState
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
        ocr_w = int(scan_res.weight_declared or 500)
        verify_res = self.api_client.verify_package(
            tracking_number=scan_res.tracking_number,
            ocr_weight=ocr_w,
        )

        if verify_res.action != "UNLOCK_DOOR" or verify_res.locker_number is None:
            self.indicators.error_sound()
            self.indicators.display_message("Rejected", verify_res.message[:16])
            self.transition_to(SystemState.ERROR)
            time.sleep(2.5)
            self.transition_to(SystemState.IDLE)
            return False

        locker_num = verify_res.locker_number
        order_id = verify_res.order_id or 1
        logger.info("Package authorized for Locker #%d (Customer: %s)", locker_num, verify_res.customer_name)

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

        measurement = self.loadcell.measure_weight_delta(locker_num, expected_weight=float(ocr_w))
        measured_int = int(measurement.current_weight_grams)

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
        otp_res = self.api_client.verify_otp(pin)

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
