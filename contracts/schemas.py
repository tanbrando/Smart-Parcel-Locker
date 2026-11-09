"""
Shared Pydantic models and Enums for the Smart Parcel Locker System.
Acts as the single source of truth contract between edge modules and server endpoints.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, model_validator


class LockerStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    OCCUPIED = "OCCUPIED"
    MAINTENANCE = "MAINTENANCE"
    ERROR = "ERROR"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    DEPOSITED = "DEPOSITED"
    RETRIEVED = "RETRIEVED"
    CANCELLED = "CANCELLED"


class SystemState(str, Enum):
    IDLE = "IDLE"
    SCANNING = "SCANNING"
    VERIFYING = "VERIFYING"
    UNLOCKED_DEPOSIT = "UNLOCKED_DEPOSIT"
    WEIGHING = "WEIGHING"
    DEPOSIT_CONFIRMED = "DEPOSIT_CONFIRMED"
    KEYPAD_INPUT = "KEYPAD_INPUT"
    RETRIEVING = "RETRIEVING"
    ERROR = "ERROR"


class DepositStatus(str, Enum):
    """Result of the edge-side parcel integrity check."""

    SUCCESS = "SUCCESS"
    EMPTY_DEPOSIT = "EMPTY_DEPOSIT"
    WEIGHT_MISMATCH = "WEIGHT_MISMATCH"
    UNSTABLE_WEIGHT = "UNSTABLE_WEIGHT"


class DepositAction(str, Enum):
    """Action requested from the edge controller after verification."""

    CONFIRM_SERVER_AND_LOCK = "CONFIRM_SERVER_AND_LOCK"
    TRIGGER_BUZZER_ALARM = "TRIGGER_BUZZER_ALARM"
    RETRY_MEASUREMENT = "RETRY_MEASUREMENT"


# ==========================================
# CV & Hardware Schemas (Edge)
# ==========================================

class ScanResult(BaseModel):
    """Result returned by CV Scanner (Person 1)."""
    tracking_number: Optional[str] = Field(None, description="Decoded parcel tracking number")
    raw_text: str = Field("", description="Raw OCR / Barcode text extracted")
    barcode_type: Optional[str] = Field(None, description="QRCODE, CODE128, etc.")
    weight_declared: Optional[float] = Field(None, description="Weight parsed from waybill label in grams")
    success: bool = Field(False, description="Whether at least one usable code was detected")
    order_code: Optional[str] = Field(None, description="Merchant order code when available")
    ocr_weight: Optional[int] = Field(None, description="OCR weight in grams, for the core contract")
    phone_last4: Optional[str] = Field(None, description="Last four recipient phone digits")
    captured_frame_path: str = Field("", description="Evidence image path captured by the edge device")
    error_code: Optional[str] = Field(None, description="NO_CODE_FOUND, TIMEOUT, or CAMERA_ERROR")
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Confidence score")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def synchronize_weight_fields(self):
        if self.ocr_weight is None and self.weight_declared is not None:
            self.ocr_weight = int(round(self.weight_declared))
        if self.weight_declared is None and self.ocr_weight is not None:
            self.weight_declared = float(self.ocr_weight)
        if self.tracking_number and not self.success:
            self.success = True
        return self


class WeightMeasurement(BaseModel):
    """Result returned by Load Cell sensor (Person 2)."""
    locker_id: int = Field(..., description="Locker index being measured")
    current_weight_grams: float = Field(0.0, description="Absolute weight currently measured")
    delta_grams: float = Field(0.0, description="Weight change since tare/door opening")
    before_weight: float = Field(0.0, description="Weight before the door was opened")
    after_weight: float = Field(0.0, description="Weight after the parcel was placed")
    delta_weight: float = Field(0.0, description="after_weight - before_weight")
    is_stable: bool = Field(True, description="Whether reading has stabilized")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def synchronize_weight_fields(self):
        if self.after_weight == 0.0 and self.current_weight_grams != 0.0:
            self.after_weight = self.current_weight_grams
        if self.current_weight_grams == 0.0 and self.after_weight != 0.0:
            self.current_weight_grams = self.after_weight
        if self.delta_weight == 0.0 and self.delta_grams != 0.0:
            self.delta_weight = self.delta_grams
        if self.delta_grams == 0.0 and self.delta_weight != 0.0:
            self.delta_grams = self.delta_weight
        return self


class LockerAuth(BaseModel):
    """Authorization returned by the server before opening a locker."""

    is_allowed: bool
    locker_id: Optional[int] = None
    order_id: Optional[str] = None
    customer_name: Optional[str] = None
    expected_weight: Optional[float] = None
    weight_tolerance: float = 150.0
    reject_reason: Optional[str] = None


class KeypadEvent(BaseModel):
    """One completed OTP entry attempt from the matrix keypad."""

    entered_pin: str = ""
    attempts_count: int = 0
    is_rate_limited: bool = False
    remaining_lock_time: int = 0


class DepositDecision(BaseModel):
    """Core decision after comparing the measured parcel with the authorization."""

    status: DepositStatus
    action: DepositAction
    message: str


# ==========================================
# Edge <-> Server API Payloads
# ==========================================

class PackageVerificationRequest(BaseModel):
    """Request sent by edge when courier presents waybill."""
    tracking_number: str
    measured_weight_grams: Optional[float] = None
    ocr_weight: Optional[float] = None
    recipient_phone_last4: Optional[str] = None
    order_code: Optional[str] = None


class PackageVerificationResponse(BaseModel):
    """Response from server authorizing locker deposit."""
    verified: bool
    order_id: Optional[str] = None
    locker_id: Optional[int] = None
    declared_weight_grams: Optional[float] = None
    tolerance_grams: float = 150.0
    message: str = ""
    action: Optional[str] = None
    reason: Optional[str] = None


class DepositConfirmationRequest(BaseModel):
    """Request sent by edge after parcel is placed and weighed."""
    order_id: str
    locker_id: int
    tracking_number: str
    final_weight_grams: float


class DepositConfirmationResponse(BaseModel):
    """Server acknowledgment of successful deposit."""
    success: bool
    order_id: str
    locker_id: int
    message: str = "Deposit confirmed successfully"


class OtpVerificationRequest(BaseModel):
    """Request sent when recipient inputs 6-digit OTP."""
    otp_code: str
    locker_id: Optional[int] = None


class OtpVerificationResponse(BaseModel):
    """Response authorizing recipient pickup."""
    success: bool
    locker_id: Optional[int] = None
    order_id: Optional[str] = None
    message: str = ""


# ==========================================
# Server & Management Models
# ==========================================

class OrderCreateRequest(BaseModel):
    """Manual or OCR-extracted order registration."""
    tracking_number: str
    recipient_name: str
    recipient_phone: str
    declared_weight_grams: float = 0.0
    telegram_chat_id: Optional[str] = None


class OrderResponse(BaseModel):
    """Full order detail representation."""
    id: str
    tracking_number: str
    recipient_name: str
    recipient_phone: str
    declared_weight_grams: float
    actual_weight_grams: Optional[float] = None
    status: OrderStatus
    locker_id: Optional[int] = None
    otp_code: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class LockerInfo(BaseModel):
    """Current state of a physical locker compartment."""
    id: int
    locker_number: str
    status: LockerStatus
    current_order_id: Optional[str] = None
    current_weight_grams: float = 0.0
    max_weight_capacity_grams: float = 5000.0

    model_config = ConfigDict(from_attributes=True)
