"""
Finite State Machine (FSM) Module [Person 3].
Orchestrates hardware drivers (Ultrasonic Sensor, Servo Lock, Indicators),
computer vision, and cloud API into a cohesive locker lifecycle.
"""
import time
import logging
from typing import Optional

from contracts.schemas import (
    DepositAction,
    DepositDecision,
    DepositStatus,
    OccupancyResult,
    ScanResult,
    SystemState,
)
from edge.cv.scanner import PackageScanner
from edge.hardware.ultrasonic_sensor import UltrasonicSensor, get_ultrasonic_sensor
from edge.hardware.servo_lock import ServoLockController, get_servo_lock
from edge.hardware.indicators import IndicatorController
from edge.core.keypad import KeypadReader
from edge.core.api_client import EdgeApiClient

logger = logging.getLogger("edge.core.fsm")


def verify_occupancy_integrity(occupancy: OccupancyResult) -> DepositDecision:
    """Validate ultrasonic occupancy result before locking and confirming deposit."""
    if occupancy.error:
        return DepositDecision(
            status=DepositStatus.UNSTABLE_WEIGHT,
            action=DepositAction.RETRY_MEASUREMENT,
            message=f"Ultrasonic sensor error: {occupancy.error}",
        )

    if not occupancy.occupied:
        return DepositDecision(
            status=DepositStatus.EMPTY_DEPOSIT,
            action=DepositAction.TRIGGER_BUZZER_ALARM,
            message="No parcel was detected in the locker.",
        )

    return DepositDecision(
        status=DepositStatus.SUCCESS,
        action=DepositAction.CONFIRM_SERVER_AND_LOCK,
        message="Parcel detected in locker successfully.",
    )


class LockerStateMachine:
    """Finite State Machine supervising the smart locker system."""

    def __init__(
        self,
        scanner: Optional[PackageScanner] = None,
        ultrasonic: Optional[UltrasonicSensor] = None,
        lock: Optional[ServoLockController] = None,
        indicators: Optional[IndicatorController] = None,
        keypad: Optional[KeypadReader] = None,
        api_client: Optional[EdgeApiClient] = None,
    ):
        self.state: SystemState = SystemState.IDLE
        self.scanner = scanner or PackageScanner()
        self.ultrasonic = ultrasonic or get_ultrasonic_sensor()
        self.lock = lock or get_servo_lock()
        self.indicators = indicators or IndicatorController()
        self.keypad = keypad or KeypadReader()
        self.api_client = api_client or EdgeApiClient()

        self._running = False
        logger.info("LockerStateMachine initialized in state %s", self.state)

    def transition_to(self, new_state: SystemState):
        logger.info("FSM Transition: %s -> %s", self.state.value, new_state.value)
        self.state = new_state

    def handle_courier_deposit(self) -> bool:
        """Executes full courier parcel drop-off workflow using Ultrasonic + Servo Lock."""
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

        # 3. Capture dynamic pre-deposit baseline, then unlock locker door (servo -> 90 deg)
        before_cm = self.ultrasonic.capture_reference_baseline(locker_id)
        self.transition_to(SystemState.UNLOCKED_DEPOSIT)
        self.indicators.success_sound()
        self.indicators.display_message(f"Locker {locker_id} Open", "Put & Press C")
        self.lock.unlock_door(locker_id)

        # 4. Wait for close key 'C' (or door switch) & check differential occupancy (delta >= 1.0cm)
        if not self.lock.wait_for_door_closed(locker_id, keypad=self.keypad):
            self.indicators.error_sound()
            self.indicators.display_message("Close Door", "Door not closed")
            self.transition_to(SystemState.ERROR)
            time.sleep(1.0)
            self.transition_to(SystemState.IDLE)
            return False

        self.indicators.display_message("Checking Locker", "Please wait...")
        occupancy = self.ultrasonic.is_locker_occupied(locker_id, reference_cm=before_cm)
        decision = verify_occupancy_integrity(occupancy)

        if decision.action != DepositAction.CONFIRM_SERVER_AND_LOCK:
            logger.warning("Deposit rejected by ultrasonic check: %s", decision.message)
            # Keep door UNLOCKED when empty or sensor error (fail-safe)
            self.lock.unlock_door(locker_id)
            if decision.action == DepositAction.TRIGGER_BUZZER_ALARM:
                self.indicators.alarm_sound()
            else:
                self.indicators.error_sound()
            self.indicators.display_message("Deposit Error", decision.message[:16])
            self.transition_to(SystemState.ERROR)
            time.sleep(2.0)
            self.transition_to(SystemState.IDLE)
            return False

        # Parcel detected and door closed -> lock servo
        self.lock.lock_door(locker_id)

        # 5. Confirm deposit to server
        order_id_int = int(order_id) if str(order_id).isdigit() else 0

        self.transition_to(SystemState.DEPOSIT_CONFIRMED)
        confirm_res = self.api_client.confirm_deposit(
            order_id=order_id_int,
            locker_number=locker_id,
            delta_weight=0,
            distance_cm=occupancy.distance_cm,
            empty_distance_cm=occupancy.baseline_cm,
        )

        if confirm_res.success:
            self.indicators.success_sound()
            self.indicators.display_message("Deposit Success!", f"Locker {locker_id} OK")
            logger.info("Deposit successfully completed for order #%s. OTP: %s", order_id, confirm_res.otp_generated)
        else:
            self.indicators.error_sound()
            self.indicators.display_message("Confirm Error", "Deposit failed")

        time.sleep(2.5)
        self.transition_to(SystemState.IDLE)
        return confirm_res.success

    def handle_recipient_pickup(
        self,
        otp_input: Optional[str] = None,
        initial_digit: Optional[str] = None,
    ) -> bool:
        """Executes recipient OTP collection workflow."""
        if self.keypad.is_locked_out():
            remain = self.keypad.get_remaining_lockout_seconds()
            self.indicators.error_sound()
            self.indicators.display_message("Locked Out", f"Wait {remain}s")
            return False

        self.transition_to(SystemState.KEYPAD_INPUT)
        self.indicators.display_message("Enter 6-digit OTP", "Press # to enter")

        pin = self.keypad.get_pin_input(
            timeout=20.0,
            mock_input=otp_input,
            initial_digits=initial_digit or "",
        )
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
            self.indicators.display_message(f"Locker {target_locker} Open", "Take & Press C")
            self.lock.open_locker_door(target_locker)
            # Wait for user to take parcel, shut door and press 'C' (or 15s auto-lock)
            self.keypad.wait_for_close_key(timeout=15.0, close_key="C")
            self.lock.lock_door(target_locker)
            self.indicators.display_message(f"Locker {target_locker} Lock", "Thank you!")
            self.ultrasonic.capture_reference_baseline(target_locker)
            time.sleep(1.5)
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

    def handle_face_pickup(self, account_id: Optional[int] = None):
        """Open the server-authorized compartment after single-look 1:N Face ID verification."""
        if self.keypad.is_locked_out():
            remain = self.keypad.get_remaining_lockout_seconds()
            self.indicators.error_sound()
            self.indicators.display_message("Locked Out", f"Wait {remain}s")
            return False

        resolved_user_id: Optional[int] = None
        if account_id is not None and str(account_id).strip():
            raw_id = str(account_id).strip()
            if not raw_id.isascii() or not raw_id.isdigit() or len(raw_id) > 10:
                return False
            resolved_user_id = int(raw_id)

        self.transition_to(SystemState.VERIFYING)
        try:
            from edge.core.face_pickup import verify_pickup

            result = verify_pickup(self.api_client, resolved_user_id, self.indicators)
            if result.valid and result.locker_number is not None:
                self.keypad.reset_attempts()
                self.transition_to(SystemState.RETRIEVING)
                locker_num = result.locker_number
                opened = bool(self.lock.open_locker_door(locker_num))
                if opened:
                    self.indicators.success_sound()
                    self.indicators.display_message(f"Locker {locker_num} Open", "Take & Press C")
                    self.keypad.wait_for_close_key(timeout=15.0, close_key="C")
                    self.lock.lock_door(locker_num)
                    self.indicators.display_message(f"Locker {locker_num} Lock", "Thank you!")
                    self.ultrasonic.capture_reference_baseline(locker_num)
                    time.sleep(1.5)
                self.transition_to(SystemState.IDLE)
                return opened
            logger.info("Face pickup rejected by server: %s", result.message)
        except (ImportError, KeyError, RuntimeError, OSError, TimeoutError, ValueError) as exc:
            logger.warning("Face pickup failed: %s", exc)
        self.keypad.record_failed_attempt()
        self.indicators.error_sound()
        self.indicators.display_message("Face ID failed", "Try again")
        self.transition_to(SystemState.ERROR)
        time.sleep(1.5)
        self.transition_to(SystemState.IDLE)
        return False

    def handle_manual_close(self) -> bool:
        """Triggered by key 'C' (S12) in IDLE: locks all currently open lockers back to 0 deg."""
        closed = self.lock.lock_all_open_doors()
        if closed:
            for lid in closed:
                self.ultrasonic.capture_reference_baseline(lid)
            self.indicators.success_sound()
            self.indicators.display_message("Locker Closed", f"Locked: {','.join(map(str, closed))}")
            logger.info("Manual close ('C'): locked open locker(s) %s", closed)
        else:
            self.indicators.beep(duration=0.06, count=1)
            self.indicators.display_message("All Locked", "No open door")
        time.sleep(1.0)
        return bool(closed)

    def reset_to_idle(self):
        """Displays ready state."""
        self.transition_to(SystemState.IDLE)
        self.indicators.display_message("Smart Locker", "*In #OTP C:Lock")
