"""
Server API and Business Logic Tests [Person 4].
Tests strict database schema, user recognition via telegram_chat_id,
edge verification, deposit confirmation with anti-fraud weight check,
and OTP rate-limiting / pickup lifecycle.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from contracts.schemas import (
    PackageVerificationRequest,
    DepositConfirmationRequest,
    OtpVerificationRequest,
    OrderStatus,
    LockerStatus,
)
from server.main import health_check
from server.db.session import Base
from server.db.models import Order, Locker, User
from server.routers import orders, edge, lockers
from server.core.security import otp_rate_limiter

# In-memory SQLite engine for blazing-fast, isolated test execution
test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def init_test_db(session):
    Base.metadata.create_all(bind=test_engine)
    # Seed users
    u1 = User(id=1, full_name="Nguyễn Minh Tấn", phone="0912343456", phone_last4="3456", telegram_chat_id=123456789)
    u2 = User(id=2, full_name="Trần Thị Hoa", phone="0987654321", phone_last4="4321", telegram_chat_id=987654321)
    session.add_all([u1, u2])

    # Seed lockers
    l1 = Locker(id=1, locker_number=1, current_weight=0, max_weight=5000, status=LockerStatus.EMPTY)
    l2 = Locker(id=2, locker_number=2, current_weight=0, max_weight=5000, status=LockerStatus.EMPTY)
    l3 = Locker(id=3, locker_number=3, current_weight=0, max_weight=5000, status=LockerStatus.EMPTY)
    session.add_all([l1, l2, l3])
    session.commit()


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=test_engine)
    db = TestingSessionLocal()
    init_test_db(db)
    db.close()
    otp_rate_limiter.reset()
    yield


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_health_endpoint():
    res = health_check()
    assert res["status"] == "ok"
    assert "Smart Parcel Locker" in res["app"]


def test_seed_data_initialization(db_session):
    users = db_session.query(User).all()
    assert len(users) >= 2
    tan_user = db_session.query(User).filter(User.telegram_chat_id == 123456789).first()
    assert tan_user is not None
    assert tan_user.full_name == "Nguyễn Minh Tấn"
    assert tan_user.phone_last4 == "3456"

    lockers_list = db_session.query(Locker).all()
    assert len(lockers_list) == 3
    for l in lockers_list:
        assert l.status == LockerStatus.EMPTY
        assert l.current_weight == 0
        assert l.max_weight == 5000


def test_register_screenshot_with_telegram_id(db_session):
    import io
    from fastapi import UploadFile

    upload_file = UploadFile(
        file=io.BytesIO(b"fake-shopee-image-data"),
        filename="SPXVN048291048_order.png",
    )

    res = orders.register_order_from_screenshot(
        image=upload_file,
        telegram_chat_id=123456789,
        expected_weight=520,
        db=db_session,
    )

    assert res.success is True
    data = res.data
    assert data.tracking_number == "SPXVN048291048"
    assert data.detected_recipient == "Nguyễn Minh Tấn"
    assert data.status == OrderStatus.REGISTERED
    assert data.order_id > 0

    # Verify database state
    saved_order = db_session.query(Order).filter(Order.id == data.order_id).first()
    assert saved_order is not None
    assert saved_order.user.telegram_chat_id == 123456789
    assert saved_order.expected_weight == 520
    assert saved_order.status == OrderStatus.REGISTERED


def test_verify_package_tracking_and_phone_fallback(db_session):
    user = db_session.query(User).filter(User.telegram_chat_id == 123456789).first()
    order = Order(
        user_id=user.id,
        tracking_number="SPXVN048291048",
        expected_weight=520,
        status=OrderStatus.REGISTERED,
    )
    db_session.add(order)
    db_session.commit()

    # 1. Match by tracking_number
    req1 = PackageVerificationRequest(tracking_number="SPXVN048291048", ocr_weight=520)
    res1 = edge.verify_package(req1, db=db_session)
    assert res1.action == "UNLOCK_DOOR"
    assert res1.locker_number == 1
    assert res1.order_id == order.id
    assert res1.customer_name == "Nguyễn Minh Tấn"

    # 2. Match by recipient_phone_last4 fallback
    order2 = Order(
        user_id=user.id,
        tracking_number="GHN888999",
        expected_weight=400,
        status=OrderStatus.REGISTERED,
    )
    db_session.add(order2)
    db_session.commit()

    req2 = PackageVerificationRequest(recipient_phone_last4="3456", ocr_weight=400)
    res2 = edge.verify_package(req2, db=db_session)
    assert res2.action == "UNLOCK_DOOR"
    assert res2.order_id == order2.id

    # 3. Reject non-existent order
    req3 = PackageVerificationRequest(tracking_number="NON_EXISTENT")
    res3 = edge.verify_package(req3, db=db_session)
    assert res3.status_code == 400


def test_full_deposit_and_anti_fraud_lifecycle(db_session):
    user = db_session.query(User).first()
    order = Order(
        user_id=user.id,
        tracking_number="SPXVN048291048",
        expected_weight=520,
        status=OrderStatus.REGISTERED,
    )
    db_session.add(order)
    db_session.commit()

    # Verify
    v_res = edge.verify_package(PackageVerificationRequest(tracking_number="SPXVN048291048", ocr_weight=520), db=db_session)
    assert v_res.action == "UNLOCK_DOOR"

    # Confirm Deposit with actual weight 495g (deviation = 25g <= 150g tolerance)
    dep_req = DepositConfirmationRequest(
        order_id=order.id,
        locker_number=1,
        delta_weight=495,
        image_base64="fake-base64-image",
    )
    dep_res = edge.confirm_deposit(dep_req, db=db_session)
    assert dep_res.success is True
    assert dep_res.status == OrderStatus.STORED
    assert dep_res.weight_matched is True
    assert dep_res.deviation_gram == 25
    otp = dep_res.otp_generated
    assert len(otp) == 6

    # Verify DB state
    db_session.refresh(order)
    assert order.status == OrderStatus.STORED
    assert order.actual_weight == 495
    assert order.otp_code == otp

    locker = db_session.query(Locker).filter(Locker.locker_number == 1).first()
    assert locker.status == LockerStatus.OCCUPIED
    assert locker.current_weight == 495


def test_otp_rate_limiting_and_pickup(db_session):
    from datetime import datetime, timedelta, timezone

    user = db_session.query(User).first()
    order = Order(
        user_id=user.id,
        tracking_number="SPXVN048291048",
        expected_weight=500,
        actual_weight=500,
        otp_code="829104",
        otp_expires_at=datetime.now(timezone.utc) + timedelta(hours=72),
        status=OrderStatus.STORED,
    )
    db_session.add(order)
    db_session.commit()

    # 1. First wrong OTP attempt
    res1 = edge.verify_otp(OtpVerificationRequest(otp_code="111111"), db=db_session)
    assert res1.status_code == 401

    # 2. Second wrong OTP attempt
    res2 = edge.verify_otp(OtpVerificationRequest(otp_code="222222"), db=db_session)
    assert res2.status_code == 401

    # 3. Third wrong OTP attempt -> Triggers lockout
    res3 = edge.verify_otp(OtpVerificationRequest(otp_code="333333"), db=db_session)
    assert res3.status_code == 401
    assert otp_rate_limiter.is_locked() is True

    # 4. Attempt while locked out -> Blocked
    res_locked = edge.verify_otp(OtpVerificationRequest(otp_code="829104"), db=db_session)
    assert res_locked.status_code == 401

    # Reset limiter for pickup test
    otp_rate_limiter.reset()

    # 5. Correct OTP -> Pickup successful
    res_success = edge.verify_otp(OtpVerificationRequest(otp_code="829104"), db=db_session)
    assert res_success.valid is True
    assert res_success.locker_number == 1

    db_session.refresh(order)
    assert order.status == OrderStatus.COLLECTED
    assert order.otp_code is None


def test_dashboard_and_static_files():
    from pathlib import Path
    from server.main import (
        REPO_ROOT,
        serve_dashboard,
        serve_lockers,
        serve_orders,
        serve_users,
        serve_logs,
        serve_simulator,
    )

    # 1. Multi-Page HTML Route Functions
    page_handlers = [
        serve_dashboard,
        serve_lockers,
        serve_orders,
        serve_users,
        serve_logs,
        serve_simulator,
    ]
    for handler in page_handlers:
        res = handler()
        assert Path(res.path).exists(), f"File {res.path} not found"
        content = Path(res.path).read_text(encoding="utf-8")
        assert "SmartLocker" in content, f"SmartLocker not in {res.path}"

    # 2. Static CSS file
    css_file = REPO_ROOT / "web" / "css" / "styles.css"
    assert css_file.exists()
    assert "--accent-yellow" in css_file.read_text(encoding="utf-8")

    # 3. Static JS files
    common_js = REPO_ROOT / "web" / "js" / "common.js"
    assert common_js.exists()
    assert "renderSharedSidebar" in common_js.read_text(encoding="utf-8")

    app_js = REPO_ROOT / "web" / "js" / "app.js"
    assert app_js.exists()
    assert "fetchAllData" in app_js.read_text(encoding="utf-8")



