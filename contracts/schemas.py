"""
Shared Pydantic models and Enums for the Smart Parcel Locker System.
Acts as the single source of truth contract between edge modules and server endpoints.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


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
# Edge <-> Server API Payloads
# ==========================================

class PackageVerificationRequest(BaseModel):
    """Request sent by edge when courier presents waybill."""
    tracking_number: str
    measured_weight_grams: Optional[float] = None


class PackageVerificationResponse(BaseModel):
    """Response from server authorizing locker deposit."""
    verified: bool
    order_id: Optional[str] = None
    locker_id: Optional[int] = None
    declared_weight_grams: Optional[float] = None
    tolerance_grams: float = 150.0
    message: str = ""


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
