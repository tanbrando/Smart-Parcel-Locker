"""
Server API and Business Logic Tests [Person 4].
Tests full parcel lifecycle: Registration -> Pi Verification -> Deposit -> OTP Pickup.
"""
import pytest
from contracts.schemas import (
    OrderCreateRequest,
    PackageVerificationRequest,
    DepositConfirmationRequest,
    OtpVerificationRequest,
    OrderStatus,
    LockerStatus,
)
from server.main import health_check, init_database_tables
from server.db.session import engine, Base, SessionLocal
from server.routers import orders, edge, lockers


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    init_database_tables()
    yield


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_health_endpoint():
    res = health_check()
    assert res["status"] == "ok"
    assert "Smart Parcel Locker" in res["app"]


def test_full_locker_deposit_and_pickup_lifecycle(db_session):
    # 1. User registers order
    req = OrderCreateRequest(
        tracking_number="SPX99988877VN",
        recipient_name="Test Recipient",
        recipient_phone="0901234567",
        declared_weight_grams=450.0,
        telegram_chat_id="test_chat_id",
    )
    created_order = orders.create_order_manual(req, db=db_session)
    assert created_order.status == OrderStatus.PENDING
    assert created_order.tracking_number == "SPX99988877VN"
    order_id = created_order.id

    # 2. Courier arrives at Pi: verify-package
    verify_req = PackageVerificationRequest(
        tracking_number="SPX99988877VN",
        measured_weight_grams=None,
    )
    verify_res = edge.verify_package(verify_req, db=db_session)
    assert verify_res.verified is True
    assert verify_res.locker_id is not None
    assigned_locker_id = verify_res.locker_id

    # 3. Parcel placed and measured: confirm-deposit
    deposit_req = DepositConfirmationRequest(
        order_id=order_id,
        locker_id=assigned_locker_id,
        tracking_number="SPX99988877VN",
        final_weight_grams=455.0,
    )
    confirm_res = edge.confirm_deposit(deposit_req, db=db_session)
    assert confirm_res.success is True

    # Check order in DB
    db_session.refresh(created_order)
    assert created_order.status == OrderStatus.DEPOSITED
    assert created_order.actual_weight_grams == 455.0
    otp_code = created_order.otp_code
    assert otp_code is not None
    assert len(otp_code) == 6

    # 4. Recipient enters wrong OTP
    wrong_otp_req = OtpVerificationRequest(otp_code="000000")
    wrong_otp_res = edge.verify_otp(wrong_otp_req, db=db_session)
    assert wrong_otp_res.success is False

    # 5. Recipient enters correct OTP
    correct_otp_req = OtpVerificationRequest(otp_code=otp_code)
    correct_otp_res = edge.verify_otp(correct_otp_req, db=db_session)
    assert correct_otp_res.success is True
    assert correct_otp_res.locker_id == assigned_locker_id

    # 6. Verify locker is now AVAILABLE again
    locker_obj = lockers.get_locker(assigned_locker_id, db=db_session)
    assert locker_obj.status == LockerStatus.AVAILABLE

    # 7. Verify access logs recorded events
    logs = lockers.get_access_logs(limit=10, db=db_session)
    assert len(logs) >= 3
