"""
Mock fixtures for Smart Parcel Locker local testing and offline emulation.
Useful for team members developing without physical hardware or server connectivity.
"""
from datetime import datetime, timezone
from contracts.schemas import (
    ScanResult,
    WeightMeasurement,
    PackageVerificationResponse,
    DepositConfirmationResponse,
    OtpVerificationResponse,
    OrderResponse,
    OrderStatus,
    LockerInfo,
    LockerStatus,
)

# Mock Waybill Scans
MOCK_SCAN_VALID_SPX = ScanResult(
    tracking_number="SPX038472918VN",
    raw_text="SPX Express - SPX038472918VN - Khoi luong: 450g",
    barcode_type="CODE128",
    weight_declared=450.0,
    confidence=0.98,
    timestamp=datetime.now(timezone.utc),
)

MOCK_SCAN_VALID_GHN = ScanResult(
    tracking_number="GHN78921820",
    raw_text="Giao Hang Nhanh Tracking: GHN78921820 Weight: 1.2kg",
    barcode_type="QRCODE",
    weight_declared=1200.0,
    confidence=0.95,
    timestamp=datetime.now(timezone.utc),
)

MOCK_SCAN_UNKNOWN = ScanResult(
    tracking_number=None,
    raw_text="Unreadable label blur blur",
    barcode_type=None,
    weight_declared=None,
    confidence=0.2,
    timestamp=datetime.now(timezone.utc),
)

# Mock Load Cell Weight Deltas
MOCK_WEIGHT_MEASUREMENT_MATCH = WeightMeasurement(
    locker_id=1,
    current_weight_grams=455.0,
    delta_grams=455.0,
    is_stable=True,
    timestamp=datetime.now(timezone.utc),
)

MOCK_WEIGHT_MEASUREMENT_EMPTY = WeightMeasurement(
    locker_id=1,
    current_weight_grams=0.0,
    delta_grams=0.0,
    is_stable=True,
    timestamp=datetime.now(timezone.utc),
)

# Mock Server API Responses
MOCK_VERIFY_RESPONSE_SUCCESS = PackageVerificationResponse(
    verified=True,
    order_id="ord-spx-001",
    locker_id=1,
    declared_weight_grams=450.0,
    tolerance_grams=100.0,
    message="Package authorized for Locker 1",
)

MOCK_VERIFY_RESPONSE_NOT_FOUND = PackageVerificationResponse(
    verified=False,
    order_id=None,
    locker_id=None,
    declared_weight_grams=None,
    tolerance_grams=100.0,
    message="Tracking number not found or already processed",
)

MOCK_DEPOSIT_RESPONSE_SUCCESS = DepositConfirmationResponse(
    success=True,
    order_id="ord-spx-001",
    locker_id=1,
    message="Parcel successfully verified and secured in locker 1",
)

MOCK_OTP_RESPONSE_SUCCESS = OtpVerificationResponse(
    success=True,
    locker_id=1,
    order_id="ord-spx-001",
    message="OTP validated. Opening locker 1",
)

# Mock Lockers & Orders
MOCK_LOCKERS = [
    LockerInfo(
        id=1,
        locker_number="L01",
        status=LockerStatus.AVAILABLE,
        current_order_id=None,
        current_weight_grams=0.0,
        max_weight_capacity_grams=5000.0,
    ),
    LockerInfo(
        id=2,
        locker_number="L02",
        status=LockerStatus.OCCUPIED,
        current_order_id="ord-existing-002",
        current_weight_grams=820.0,
        max_weight_capacity_grams=5000.0,
    ),
    LockerInfo(
        id=3,
        locker_number="L03",
        status=LockerStatus.MAINTENANCE,
        current_order_id=None,
        current_weight_grams=0.0,
        max_weight_capacity_grams=5000.0,
    ),
]

MOCK_ORDERS = [
    OrderResponse(
        id="ord-spx-001",
        tracking_number="SPX038472918VN",
        recipient_name="Nguyen Van A",
        recipient_phone="0912345678",
        declared_weight_grams=450.0,
        actual_weight_grams=None,
        status=OrderStatus.PENDING,
        locker_id=None,
        otp_code=None,
        telegram_chat_id="123456789",
        created_at=datetime.now(timezone.utc),
    ),
    OrderResponse(
        id="ord-existing-002",
        tracking_number="GHN78921820",
        recipient_name="Tran Thi B",
        recipient_phone="0987654321",
        declared_weight_grams=800.0,
        actual_weight_grams=820.0,
        status=OrderStatus.DEPOSITED,
        locker_id=2,
        otp_code="582194",
        telegram_chat_id="987654321",
        created_at=datetime.now(timezone.utc),
    ),
]
