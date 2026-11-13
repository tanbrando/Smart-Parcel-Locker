"""
Edge API Client Module [Person 3].
Communicates with the Cloud / Central FastAPI Server (Person 4).
"""
import logging
from typing import Optional
import requests

from contracts.schemas import (
    LockerAuth,
    ScanResult,
    PackageVerificationRequest,
    PackageVerificationResponse,
    DepositConfirmationRequest,
    DepositConfirmationResponse,
    OtpVerificationRequest,
    OtpVerificationResponse,
)
from edge.config import SERVER_API_URL, API_TIMEOUT_SECONDS

logger = logging.getLogger("edge.core.api_client")


class EdgeApiClient:
    """Client for edge-to-cloud server communication."""

    def __init__(self, base_url: str = SERVER_API_URL, timeout: float = API_TIMEOUT_SECONDS):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def check_health(self) -> bool:
        """Verifies server connectivity."""
        try:
            resp = requests.get(f"{self.base_url}/health", timeout=self.timeout)
            return resp.status_code == 200
        except requests.RequestException as exc:
            logger.warning("Server unreachable: %s", exc)
            return False

    def verify_package(
        self,
        tracking_number: Optional[str] = None,
        ocr_weight: int = 0,
        recipient_phone_last4: Optional[str] = None,
        measured_weight: Optional[float] = None,
        order_code: Optional[str] = None,
    ) -> PackageVerificationResponse:
        """Asks server to verify courier's waybill tracking code or phone last 4."""
        url = f"{self.base_url}/api/v1/pi/verify-package"
        eff_weight = int(round(ocr_weight)) if ocr_weight else (int(round(measured_weight)) if measured_weight is not None else 0)
        payload = PackageVerificationRequest(
            tracking_number=tracking_number,
            ocr_weight=eff_weight,
            recipient_phone_last4=recipient_phone_last4,
            measured_weight_grams=int(round(measured_weight)) if measured_weight is not None else None,
            order_code=order_code,
        ).model_dump()

        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
            if resp.status_code == 200:
                return PackageVerificationResponse(**resp.json())
            else:
                logger.error("Verify package HTTP %d: %s", resp.status_code, resp.text)
                return PackageVerificationResponse(
                    action="REJECT",
                    verified=False,
                    reason=f"HTTP_{resp.status_code}",
                    message=f"Server returned status {resp.status_code}",
                )
        except requests.RequestException as exc:
            logger.error("Network error during verify_package: %s", exc)
            return PackageVerificationResponse(
                action="REJECT",
                verified=False,
                reason="NETWORK_ERROR",
                message=f"Network error: {str(exc)}",
            )

    def request_door_unlock(self, scan_data: ScanResult) -> LockerAuth:
        """Translate the scanner contract into a server authorization request."""
        tracking_number = scan_data.tracking_number
        if not tracking_number:
            return LockerAuth(is_allowed=False, reject_reason="NO_TRACKING_NUMBER")

        eff_w = scan_data.ocr_weight or (int(round(scan_data.weight_declared)) if scan_data.weight_declared else 0)
        response = self.verify_package(
            tracking_number=tracking_number,
            ocr_weight=eff_w,
            measured_weight=scan_data.weight_declared or scan_data.ocr_weight,
            recipient_phone_last4=scan_data.phone_last4,
            order_code=scan_data.order_code,
        )
        is_allowed = bool(response.verified or response.action == "UNLOCK_DOOR")
        exp_weight = (
            float(response.declared_weight_grams)
            if response.declared_weight_grams is not None and response.declared_weight_grams > 0
            else None
        )
        max_allowed = float(response.max_allowed_weight) if response.max_allowed_weight else 5000.0
        return LockerAuth(
            is_allowed=is_allowed,
            locker_id=response.locker_id or response.locker_number,
            order_id=response.order_id,
            customer_name=response.customer_name,
            expected_weight=exp_weight,
            max_allowed_weight=max_allowed,
            weight_tolerance=response.tolerance_grams if hasattr(response, "tolerance_grams") else 150.0,
            reject_reason=response.reason if not is_allowed else None,
        )

    def handle_otp_submission(self, pin: str) -> OtpVerificationResponse:
        """Verify an OTP and return the server decision to the FSM."""
        normalized_pin = pin.strip()
        if not normalized_pin.isdigit() or len(normalized_pin) != 6:
            return OtpVerificationResponse(
                valid=False,
                success=False,
                message="OTP must contain exactly 6 digits.",
            )
        return self.verify_otp(normalized_pin)

    def confirm_deposit(
        self,
        order_id: int,
        locker_number: int,
        delta_weight: int,
        image_base64: Optional[str] = None,
    ) -> DepositConfirmationResponse:
        """Informs server that courier has placed parcel and door is closed."""
        url = f"{self.base_url}/api/v1/pi/confirm-deposit"
        payload = DepositConfirmationRequest(
            order_id=order_id,
            locker_number=locker_number,
            delta_weight=delta_weight,
            image_base64=image_base64,
        ).model_dump()

        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
            if resp.status_code == 200:
                return DepositConfirmationResponse(**resp.json())
            else:
                return DepositConfirmationResponse(
                    success=False,
                    status="REJECTED",
                    otp_generated="",
                    weight_matched=False,
                    deviation_gram=0,
                )
        except requests.RequestException as exc:
            logger.error("Network error during confirm_deposit: %s", exc)
            return DepositConfirmationResponse(
                success=False,
                status="REJECTED",
                otp_generated="",
                weight_matched=False,
                deviation_gram=0,
            )

    def verify_otp(self, otp_code: str) -> OtpVerificationResponse:
        """Verifies recipient's pickup OTP with server."""
        url = f"{self.base_url}/api/v1/pi/verify-otp"
        payload = OtpVerificationRequest(otp_code=otp_code).model_dump()

        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
            data = resp.json()
            return OtpVerificationResponse(**data)
        except requests.RequestException as exc:
            logger.error("Network error during verify_otp: %s", exc)
            return OtpVerificationResponse(
                valid=False,
                is_locked=False,
                message=f"Network error: {str(exc)}",
            )
