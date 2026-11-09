"""
Shared Pydantic models and Enums for the Smart Parcel Locker System.
Acts as the single source of truth contract between edge modules and server endpoints.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field, ConfigDict


class LockerStatus(str, Enum):
    EMPTY = "EMPTY"
    OCCUPIED = "OCCUPIED"
    MAINTENANCE = "MAINTENANCE"


class OrderStatus(str, Enum):
    REGISTERED = "REGISTERED"
    STORED = "STORED"
    COLLECTED = "COLLECTED"
    REJECTED = "REJECTED"


class AccessAction(str, Enum):
    SHIPPER_SCAN = "SHIPPER_SCAN"
    DOOR_OPEN = "DOOR_OPEN"
    WEIGHT_CHECK_FAIL = "WEIGHT_CHECK_FAIL"
    OTP_FAIL = "OTP_FAIL"
    COLLECTED = "COLLECTED"


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


# ==========================================
# CV & Hardware Schemas (Edge)
# ==========================================

class ScanResult(BaseModel):
    """Result returned by CV Scanner (Person 1)."""
    tracking_number: Optional[str] = Field(None, description="Decoded parcel tracking number")
    raw_text: str = Field("", description="Raw OCR / Barcode text extracted")
    barcode_type: Optional[str] = Field(None, description="QRCODE, CODE128, etc.")
    weight_declared: Optional[float] = Field(None, description="Weight parsed from waybill label in grams")
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Confidence score")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WeightMeasurement(BaseModel):
    """Result returned by Load Cell sensor (Person 2)."""
    locker_id: int = Field(..., description="Locker index being measured")
    current_weight_grams: float = Field(..., description="Absolute weight currently measured")
    delta_grams: float = Field(..., description="Weight change since tare/door opening")
    is_stable: bool = Field(True, description="Whether reading has stabilized")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ==========================================
# User Layer (Screenshot Registration)
# ==========================================

class ScreenshotRegisterData(BaseModel):
    order_id: int
    tracking_number: Optional[str] = None
    order_code: Optional[str] = None
    detected_recipient: str
    status: OrderStatus
    message: str


class ScreenshotRegisterResponse(BaseModel):
    success: bool
    data: ScreenshotRegisterData


# ==========================================
# Edge <-> Server API Payloads (Person 4 Contract)
# ==========================================

class PackageVerificationRequest(BaseModel):
    """Request sent by edge when courier presents waybill."""
    tracking_number: Optional[str] = None
    ocr_weight: int = Field(0, description="Declared/OCR weight in grams")
    recipient_phone_last4: Optional[str] = None


class PackageVerificationResponse(BaseModel):
    """Response from server authorizing locker deposit."""
    action: str = Field(..., description="'UNLOCK_DOOR' or 'REJECT'")
    locker_number: Optional[int] = None
    order_id: Optional[int] = None
    customer_name: Optional[str] = None
    max_allowed_weight: Optional[int] = None
    reason: Optional[str] = None
    message: str = ""


class DepositConfirmationRequest(BaseModel):
    """Request sent by edge after parcel is placed and weighed."""
    order_id: int
    locker_number: int
    delta_weight: int
    image_base64: Optional[str] = None


class DepositConfirmationResponse(BaseModel):
    """Server acknowledgment of successful deposit."""
    success: bool
    status: OrderStatus
    otp_generated: str
    weight_matched: bool
    deviation_gram: int


class OtpVerificationRequest(BaseModel):
    """Request sent when recipient inputs 6-digit OTP."""
    otp_code: str


class OtpVerificationResponse(BaseModel):
    """Response authorizing recipient pickup."""
    valid: bool
    locker_number: Optional[int] = None
    order_id: Optional[int] = None
    remaining_attempts: Optional[int] = None
    is_locked: Optional[bool] = None
    message: str = ""


# ==========================================
# Management & Entity Models
# ==========================================

class UserResponse(BaseModel):
    id: int
    full_name: str
    phone: str
    phone_last4: str
    telegram_chat_id: Optional[int] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrderResponse(BaseModel):
    """Full order detail representation."""
    id: int
    user_id: int
    locker_id: Optional[int] = None
    tracking_number: Optional[str] = None
    order_code: Optional[str] = None
    expected_weight: int = 0
    actual_weight: Optional[int] = None
    otp_code: Optional[str] = None
    otp_expires_at: Optional[datetime] = None
    status: OrderStatus
    screenshot_url: Optional[str] = None
    delivered_photo_url: Optional[str] = None
    created_at: datetime
    delivered_at: Optional[datetime] = None
    collected_at: Optional[datetime] = None
    recipient_name: Optional[str] = None
    recipient_phone: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class LockerInfo(BaseModel):
    """Current state of a physical locker compartment."""
    id: int
    locker_number: int
    current_weight: int = 0
    max_weight: int = 5000
    status: LockerStatus
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AccessLogResponse(BaseModel):
    id: int
    locker_id: Optional[int] = None
    order_id: Optional[int] = None
    action: str
    details: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
