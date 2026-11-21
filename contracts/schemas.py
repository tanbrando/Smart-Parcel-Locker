"""
Shared Pydantic models and Enums for the Smart Parcel Locker System.
Acts as the single source of truth contract between edge modules and server endpoints.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Any, Union, List, Dict
from pydantic import BaseModel, Field, ConfigDict, model_validator


class UserRole(str, Enum):
    USER = "USER"
    ADMIN = "ADMIN"


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
# Ultrasonic Sensor & Servo Lock Schemas
# ==========================================

class LockState(str, Enum):
    LOCKED = "LOCKED"
    UNLOCKED = "UNLOCKED"


class LockDecision(str, Enum):
    LOCKED = "LOCKED"
    EMPTY_NOT_LOCKED = "EMPTY_NOT_LOCKED"
    DOOR_OPEN = "DOOR_OPEN"


class OccupancyResult(BaseModel):
    """Result returned by Ultrasonic Sensor."""
    occupied: bool = Field(..., description="Whether parcel is detected inside locker")
    distance_cm: Optional[float] = Field(None, description="Measured distance in cm")
    baseline_cm: float = Field(..., description="Calibrated empty locker distance in cm")
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Reading stability confidence (0-1)")
    error: Optional[str] = Field(None, description="Error message, e.g. SENSOR_TIMEOUT")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))



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
    order_id: Optional[Union[int, str]] = None
    customer_name: Optional[str] = None
    expected_weight: Optional[float] = None
    max_allowed_weight: Optional[float] = 5000.0
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
    measured_weight_grams: Optional[int] = None
    order_code: Optional[str] = None


class PackageVerificationResponse(BaseModel):
    """Response from server authorizing locker deposit."""
    action: str = Field(default="REJECT", description="'UNLOCK_DOOR' or 'REJECT'")
    locker_number: Optional[int] = None
    order_id: Optional[int] = None
    customer_name: Optional[str] = None
    max_allowed_weight: Optional[int] = None
    reason: Optional[str] = None
    message: str = ""
    # Aliases & synchronization fields for edge compatibility
    verified: Optional[bool] = None
    locker_id: Optional[int] = None
    declared_weight_grams: Optional[int] = None
    tolerance_grams: float = 150.0

    @model_validator(mode="after")
    def sync_contract_fields(self):
        # Sync verified <-> action
        if self.verified is None:
            self.verified = (self.action == "UNLOCK_DOOR")
        elif not self.action or self.action == "REJECT":
            self.action = "UNLOCK_DOOR" if self.verified else "REJECT"

        # Sync locker_id <-> locker_number
        if self.locker_id is None and self.locker_number is not None:
            self.locker_id = self.locker_number
        elif self.locker_number is None and self.locker_id is not None:
            self.locker_number = self.locker_id

        # Sync declared_weight_grams <-> max_allowed_weight
        if self.declared_weight_grams is None and self.max_allowed_weight is not None:
            self.declared_weight_grams = self.max_allowed_weight
        elif self.max_allowed_weight is None and self.declared_weight_grams is not None:
            self.max_allowed_weight = self.declared_weight_grams

        return self


class DepositConfirmationRequest(BaseModel):
    """Request sent by edge after parcel is placed, measured by HC-SR04, and door is closed."""
    order_id: int
    locker_number: int
    delta_weight: Optional[int] = 0
    distance_cm: Optional[float] = Field(None, description="HC-SR04 ultrasonic distance measured in cm")
    empty_distance_cm: Optional[float] = Field(None, description="Baseline empty locker distance in cm")
    image_base64: Optional[str] = None


class DepositConfirmationResponse(BaseModel):
    """Server acknowledgment of successful deposit."""
    success: bool
    status: OrderStatus
    otp_generated: str
    weight_matched: bool = True
    deviation_gram: int = 0
    distance_cm: Optional[float] = None
    parcel_detected: bool = True


class OtpVerificationRequest(BaseModel):
    """Request sent when recipient inputs 6-digit OTP."""
    otp_code: str


class OtpVerificationResponse(BaseModel):
    """Response authorizing recipient pickup."""
    valid: bool = False
    success: Optional[bool] = None
    locker_number: Optional[int] = None
    locker_id: Optional[int] = None
    order_id: Optional[int] = None
    remaining_attempts: Optional[int] = None
    is_locked: Optional[bool] = None
    message: str = ""

    @model_validator(mode="after")
    def sync_otp_fields(self):
        if self.success is None:
            self.success = self.valid
        elif not self.valid and self.success is not None:
            self.valid = self.success

        if self.locker_id is None and self.locker_number is not None:
            self.locker_id = self.locker_number
        elif self.locker_number is None and self.locker_id is not None:
            self.locker_number = self.locker_id

        return self


# ==========================================
# Management & Entity Models
# ==========================================

class UserCreateRequest(BaseModel):
    """Payload for registering a new system user."""
    full_name: str
    phone: str
    telegram_chat_id: Optional[int] = None
    password: Optional[str] = "123456"
    role: UserRole = UserRole.USER


class UserResponse(BaseModel):
    id: int
    full_name: str
    phone: str
    phone_last4: str
    role: UserRole = UserRole.USER
    telegram_chat_id: Optional[int] = None
    face_auth_enabled: bool = False
    face_registered: bool = False
    face_angles_enrolled: List[str] = Field(default_factory=list)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    """Credentials for User or Admin web login."""
    phone: str
    password: str


class LoginResponse(BaseModel):
    """Authentication response with session token and role-based redirect."""
    success: bool
    token: str
    user: UserResponse
    redirect_url: str


class FaceToggleRequest(BaseModel):
    """Enable or disable facial authentication for a user."""
    user_id: int
    enabled: bool


class FaceEnrollMultiAngleRequest(BaseModel):
    """Multi-angle (5 angles) facial enrollment payload."""
    user_id: int
    angles: Dict[str, str] = Field(
        ...,
        description="Mapping of angle key ('front', 'left', 'right', 'up', 'down') to base64 image data",
    )


class FaceEnrollResponse(BaseModel):
    """Status response after enrolling or toggling facial authentication."""
    success: bool
    user_id: int
    face_auth_enabled: bool
    face_registered: bool
    enrolled_angles: List[str] = Field(default_factory=list)
    message: str


class UserNotificationItem(BaseModel):
    """Notification item for delivered/stored orders with OTP details."""
    order_id: int
    tracking_number: str
    order_code: Optional[str] = None
    locker_number: Optional[int] = None
    otp_code: Optional[str] = None
    status: OrderStatus
    delivered_at: Optional[datetime] = None
    collected_at: Optional[datetime] = None
    shared_locker_count: int = 1
    message: str


class OrderResponse(BaseModel):
    """Full order detail representation."""
    id: int
    user_id: int
    locker_id: Optional[int] = None
    tracking_number: Optional[str] = None
    order_code: Optional[str] = None
    expected_weight: int = 0
    actual_weight: Optional[int] = None
    measured_distance_cm: Optional[float] = None
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
    current_distance_cm: Optional[float] = 35.0
    empty_distance_cm: float = 35.0
    fill_percent: int = 0
    status: LockerStatus
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def compute_fill_percent(self):
        empty_d = self.empty_distance_cm if self.empty_distance_cm and self.empty_distance_cm > 0 else 35.0
        cur_d = self.current_distance_cm if self.current_distance_cm is not None else empty_d
        if self.status == LockerStatus.EMPTY:
            self.fill_percent = 0
        else:
            ratio = (empty_d - cur_d) / empty_d
            self.fill_percent = max(5, min(100, int(round(ratio * 100))))
        return self


class AccessLogResponse(BaseModel):
    id: int
    locker_id: Optional[int] = None
    order_id: Optional[int] = None
    action: str
    details: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
