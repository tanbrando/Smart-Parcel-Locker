"""
Edge API Client Module [Person 3].
Communicates with the Cloud / Central FastAPI Server.
"""
import logging
from typing import Optional
import requests

from contracts.schemas import (
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
        self, tracking_number: str, measured_weight: Optional[float] = None
    ) -> PackageVerificationResponse:
        """Asks server to verify courier's waybill tracking code."""
        url = f"{self.base_url}/api/v1/pi/verify-package"
        payload = PackageVerificationRequest(
            tracking_number=tracking_number,
            measured_weight_grams=measured_weight,
        ).model_dump()

        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
            if resp.status_code == 200:
                return PackageVerificationResponse(**resp.json())
            else:
                logger.error("Verify package HTTP %d: %s", resp.status_code, resp.text)
                return PackageVerificationResponse(
                    verified=False,
                    message=f"Server returned status {resp.status_code}",
                )
        except requests.RequestException as exc:
            logger.error("Network error during verify_package: %s", exc)
            return PackageVerificationResponse(
                verified=False,
                message=f"Network error: {str(exc)}",
            )

    def confirm_deposit(
        self, order_id: str, locker_id: int, tracking_number: str, final_weight: float
    ) -> DepositConfirmationResponse:
        """Informs server that courier has placed parcel and door is closed."""
        url = f"{self.base_url}/api/v1/pi/confirm-deposit"
        payload = DepositConfirmationRequest(
            order_id=order_id,
            locker_id=locker_id,
            tracking_number=tracking_number,
            final_weight_grams=final_weight,
        ).model_dump()

        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
            if resp.status_code == 200:
                return DepositConfirmationResponse(**resp.json())
            else:
                return DepositConfirmationResponse(
                    success=False,
                    order_id=order_id,
                    locker_id=locker_id,
                    message=f"Server error: {resp.status_code}",
                )
        except requests.RequestException as exc:
            logger.error("Network error during confirm_deposit: %s", exc)
            return DepositConfirmationResponse(
                success=False,
                order_id=order_id,
                locker_id=locker_id,
                message=f"Network error: {str(exc)}",
            )

    def verify_otp(self, otp_code: str, locker_id: Optional[int] = None) -> OtpVerificationResponse:
        """Verifies recipient's pickup OTP with server."""
        url = f"{self.base_url}/api/v1/pi/verify-otp"
        payload = OtpVerificationRequest(
            otp_code=otp_code,
            locker_id=locker_id,
        ).model_dump()

        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
            if resp.status_code == 200:
                return OtpVerificationResponse(**resp.json())
            else:
                return OtpVerificationResponse(
                    success=False,
                    message=f"Server error: {resp.status_code}",
                )
        except requests.RequestException as exc:
            logger.error("Network error during verify_otp: %s", exc)
            return OtpVerificationResponse(
                success=False,
                message=f"Network error: {str(exc)}",
            )

