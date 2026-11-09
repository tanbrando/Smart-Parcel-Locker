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
    tracking_number="SPXVN048291048",
    raw_text="SPX Express - SPXVN048291048 - Khoi luong: 520g",
    barcode_type="CODE128",
    weight_declared=520.0,
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
    current_weight_grams=495.0,
    delta_grams=495.0,
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
    action="UNLOCK_DOOR",
    locker_number=1,
    order_id=105,
    customer_name="Minh Tấn",
    max_allowed_weight=5000,
    message="Mở ngăn số 1",
)

MOCK_VERIFY_RESPONSE_REJECT = PackageVerificationResponse(
    action="REJECT",
    reason="ORDER_NOT_FOUND_OR_LOCKER_FULL",
    message="Đơn chưa đăng ký hoặc tủ đã đầy!",
)

MOCK_DEPOSIT_RESPONSE_SUCCESS = DepositConfirmationResponse(
    success=True,
    status=OrderStatus.STORED,
    otp_generated="829104",
    weight_matched=True,
    deviation_gram=25,
)

MOCK_OTP_RESPONSE_SUCCESS = OtpVerificationResponse(
    valid=True,
    locker_number=1,
    order_id=105,
    message="Mã chính xác. Đang mở ngăn số 1.",
)

# Mock Lockers & Orders
MOCK_LOCKERS = [
    LockerInfo(
        id=1,
        locker_number=1,
        status=LockerStatus.EMPTY,
        current_weight=0,
        max_weight=5000,
        updated_at=datetime.now(timezone.utc),
    ),
    LockerInfo(
        id=2,
        locker_number=2,
        status=LockerStatus.OCCUPIED,
        current_weight=820,
        max_weight=5000,
        updated_at=datetime.now(timezone.utc),
    ),
    LockerInfo(
        id=3,
        locker_number=3,
        status=LockerStatus.MAINTENANCE,
        current_weight=0,
        max_weight=5000,
        updated_at=datetime.now(timezone.utc),
    ),
]

MOCK_ORDERS = [
    OrderResponse(
        id=101,
        user_id=1,
        locker_id=None,
        tracking_number="SPXVN048291048",
        order_code="2610248K9J2L",
        expected_weight=520,
        actual_weight=None,
        otp_code=None,
        status=OrderStatus.REGISTERED,
        created_at=datetime.now(timezone.utc),
        recipient_name="Nguyễn Minh Tấn",
        recipient_phone="0912343456",
    ),
    OrderResponse(
        id=102,
        user_id=2,
        locker_id=2,
        tracking_number="GHN78921820",
        order_code="189201ABCD",
        expected_weight=800,
        actual_weight=820,
        otp_code="582194",
        status=OrderStatus.STORED,
        created_at=datetime.now(timezone.utc),
        recipient_name="Trần Thị Hoa",
        recipient_phone="0987654321",
    ),
]
