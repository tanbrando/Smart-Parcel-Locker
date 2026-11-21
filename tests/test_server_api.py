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
    from server.core.security import hash_password

    Base.metadata.create_all(bind=test_engine)
    # Seed users
    u1 = User(
        id=1,
        full_name="Nguyễn Minh Tấn",
        phone="0912343456",
        phone_last4="3456",
        role="USER",
        password_hash=hash_password("123456"),
        telegram_chat_id=123456789,
    )
    u2 = User(
        id=2,
        full_name="Trần Thị Hoa",
        phone="0987654321",
        phone_last4="4321",
        role="USER",
        password_hash=hash_password("123456"),
        telegram_chat_id=987654321,
    )
    admin = User(
        id=3,
        full_name="Quản Trị Viên Trạm",
        phone="0900000000",
        phone_last4="0000",
        role="ADMIN",
        password_hash=hash_password("admin123"),
        telegram_chat_id=None,
    )
    session.add_all([u1, u2, admin])

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


def test_create_user_endpoint(db_session):
    from contracts.schemas import UserCreateRequest

    payload = UserCreateRequest(
        full_name="Do Van A",
        phone="0933112233",
        telegram_chat_id=998877,
    )
    user = orders.create_user(payload=payload, db=db_session)
    assert user.full_name == "Do Van A"
    assert user.phone == "0933112233"
    assert user.phone_last4 == "2233"
    assert user.telegram_chat_id == 998877


def test_lockers_maintenance_and_logs(db_session):
    # Test toggle maintenance
    locker = lockers.toggle_maintenance(locker_number=2, db=db_session)
    assert locker.status == LockerStatus.MAINTENANCE

    locker_back = lockers.toggle_maintenance(locker_number=2, db=db_session)
    assert locker_back.status == LockerStatus.EMPTY

    # Test get logs
    logs = lockers.get_access_logs(limit=10, db=db_session)
    assert isinstance(logs, list)

    # Ensure /logs is registered BEFORE /{locker_number} so FastAPI doesn't return 422
    route_paths = [r.path for r in lockers.router.routes]
    assert route_paths.index("/lockers/logs") < route_paths.index("/lockers/{locker_number}")


def test_screenshot_ocr_service_details():
    from server.services.ocr_service import ScreenshotOcrService

    details = ScreenshotOcrService.parse_screenshot_details(b"mock_bytes", filename="SPXVN0123456789.png")
    assert details["tracking_number"] == "SPXVN0123456789"
    assert "order_code" in details
    assert "expected_weight" in details


def test_multi_parcel_same_user_same_locker_shared_otp(db_session):
    """Multiple orders for the same user go into the same locker and keep the exact same OTP."""
    u1 = db_session.query(User).filter(User.id == 1).first()
    u2 = db_session.query(User).filter(User.id == 2).first()

    o1 = Order(user_id=u1.id, tracking_number="SPX_BATCH_001", expected_weight=600, status=OrderStatus.REGISTERED)
    o2 = Order(user_id=u1.id, tracking_number="SPX_BATCH_002", expected_weight=700, status=OrderStatus.REGISTERED)
    o3 = Order(user_id=u2.id, tracking_number="SPX_OTHER_003", expected_weight=500, status=OrderStatus.REGISTERED)
    db_session.add_all([o1, o2, o3])
    db_session.commit()

    # 1. Shipper verifies & deposits Order 1 (User 1) -> Locker #1
    v1 = edge.verify_package(PackageVerificationRequest(tracking_number="SPX_BATCH_001", ocr_weight=600), db=db_session)
    assert v1.action == "UNLOCK_DOOR"
    assert v1.locker_number == 1

    d1 = edge.confirm_deposit(
        DepositConfirmationRequest(order_id=o1.id, locker_number=1, delta_weight=610),
        db=db_session,
    )
    assert d1.success is True
    first_otp = d1.otp_generated
    assert len(first_otp) == 6

    # 2. Shipper verifies & deposits Order 2 (same User 1) -> MUST reuse Locker #1 and keep first_otp unchanged
    v2 = edge.verify_package(PackageVerificationRequest(tracking_number="SPX_BATCH_002", ocr_weight=700), db=db_session)
    assert v2.action == "UNLOCK_DOOR"
    assert v2.locker_number == 1

    d2 = edge.confirm_deposit(
        DepositConfirmationRequest(order_id=o2.id, locker_number=1, delta_weight=690),
        db=db_session,
    )
    assert d2.success is True
    assert d2.otp_generated == first_otp  # OTP unchanged!

    # Verify locker weight accumulated and notifications report shared_locker_count == 2
    locker1 = db_session.query(Locker).filter(Locker.locker_number == 1).first()
    assert locker1.current_weight == 1300
    assert locker1.status == LockerStatus.OCCUPIED

    notifs = orders.get_user_notifications(user_id=u1.id, db=db_session)
    assert len(notifs) == 2
    assert all(n.otp_code == first_otp and n.shared_locker_count == 2 for n in notifs)

    # 3. Shipper verifies Order 3 (different User 2) -> MUST NOT enter Locker #1, gets Locker #2
    v3 = edge.verify_package(PackageVerificationRequest(tracking_number="SPX_OTHER_003", ocr_weight=500), db=db_session)
    assert v3.action == "UNLOCK_DOOR"
    assert v3.locker_number == 2

    # 4. User 1 enters shared OTP -> BOTH Order 1 and Order 2 become COLLECTED, Locker #1 becomes EMPTY
    pickup = edge.verify_otp(OtpVerificationRequest(otp_code=first_otp), db=db_session)
    assert pickup.valid is True
    assert pickup.locker_number == 1

    db_session.refresh(o1)
    db_session.refresh(o2)
    db_session.refresh(locker1)
    assert o1.status == OrderStatus.COLLECTED
    assert o2.status == OrderStatus.COLLECTED
    assert o1.otp_code is None
    assert o2.otp_code is None
    assert locker1.status == LockerStatus.EMPTY
    assert locker1.current_weight == 0


def test_auth_login_user_and_admin(db_session):
    from fastapi import HTTPException
    from contracts.schemas import LoginRequest, UserRole
    from server.routers import auth

    # User login
    u_res = auth.login(LoginRequest(phone="0912343456", password="123456"), db=db_session)
    assert u_res.success is True
    assert u_res.user.role == UserRole.USER
    assert u_res.redirect_url == "/portal"

    # Admin login
    a_res = auth.login(LoginRequest(phone="0900000000", password="admin123"), db=db_session)
    assert a_res.success is True
    assert a_res.user.role == UserRole.ADMIN
    assert a_res.redirect_url == "/"

    # Wrong password raises 401
    with pytest.raises(HTTPException) as exc:
        auth.login(LoginRequest(phone="0912343456", password="wrong"), db=db_session)
    assert exc.value.status_code == 401


def test_face_auth_toggle_and_multi_angle_enrollment(db_session, monkeypatch):
    from fastapi import HTTPException
    from contracts.schemas import FaceToggleRequest, FaceEnrollMultiAngleRequest
    from server.routers import auth
    from server.core.security import create_session_token
    import numpy as np

    authorization = "Bearer " + create_session_token(1, "USER")

    # Cannot enable Face ID before enrolling 5 angles
    with pytest.raises(HTTPException) as exc_before:
        auth.toggle_face_auth(FaceToggleRequest(user_id=1, enabled=True), db=db_session,
                              authorization=authorization)
    assert exc_before.value.status_code == 400

    # Incomplete angles rejected
    with pytest.raises(HTTPException) as exc_partial:
        auth.enroll_face_multi_angle(
            FaceEnrollMultiAngleRequest(user_id=1, angles={"front": "data:image/jpeg;base64,abc"}),
            db=db_session,
            authorization=authorization,
        )
    assert exc_partial.value.status_code == 400

    # Full 5-angle enrollment succeeds and activates Face ID
    five_angles = {
        "front": "data:image/jpeg;base64,front_img",
        "left": "data:image/jpeg;base64,left_img",
        "right": "data:image/jpeg;base64,right_img",
        "up": "data:image/jpeg;base64,up_img",
        "down": "data:image/jpeg;base64,down_img",
    }
    template = np.eye(128, dtype=np.float32)[0]
    monkeypatch.setattr(auth, "extract_templates", lambda angles: ("model", dict.fromkeys(angles, template)))
    enroll_res = auth.enroll_face_multi_angle(
        FaceEnrollMultiAngleRequest(user_id=1, angles=five_angles),
        db=db_session,
        authorization=authorization,
    )
    assert enroll_res.success is True
    assert enroll_res.face_registered is True
    assert enroll_res.face_auth_enabled is True
    assert set(enroll_res.enrolled_angles) == set(five_angles.keys())

    # Toggle off and back on
    off_res = auth.toggle_face_auth(FaceToggleRequest(user_id=1, enabled=False), db=db_session,
                                   authorization=authorization)
    assert off_res.face_auth_enabled is False
    on_res = auth.toggle_face_auth(FaceToggleRequest(user_id=1, enabled=True), db=db_session,
                                  authorization=authorization)
    assert on_res.face_auth_enabled is True

    from server.routers import edge

    db_session.add(Order(user_id=1, locker_id=1, tracking_number="FACE-PICKUP-001",
                         status=OrderStatus.STORED))
    db_session.commit()
    monkeypatch.setenv("FACE_DEVICE_KEY", "test-device")
    monkeypatch.setattr(edge.notifier, "notify_parcel_collected", lambda **kwargs: None)
    pickup = FaceEnrollMultiAngleRequest(user_id=1, angles=five_angles)
    with pytest.raises(HTTPException) as unauthorized:
        edge.verify_face(pickup, db=db_session, device_key="wrong")
    assert unauthorized.value.status_code == 403

    wrong = np.eye(128, dtype=np.float32)[1]
    probes = dict.fromkeys(five_angles, template)
    monkeypatch.setattr(edge, "extract_templates", lambda _: ("model", probes))
    probes["down"] = wrong
    assert not edge.verify_face(pickup, db=db_session, device_key="test-device").valid
    assert db_session.query(Order).filter_by(tracking_number="FACE-PICKUP-001").one().status == OrderStatus.STORED

    probes["down"] = template
    result = edge.verify_face(pickup, db=db_session, device_key="test-device")
    assert result.valid and result.locker_number == 1
    assert not edge.verify_face(pickup, db=db_session, device_key="test-device").valid


def test_modular_web_portal_and_login_assets():
    from pathlib import Path
    from server.main import REPO_ROOT, serve_login, serve_portal

    for handler in (serve_login, serve_portal):
        res = handler()
        assert Path(res.path).exists(), f"Missing page: {res.path}"
        assert "SmartLocker" in Path(res.path).read_text(encoding="utf-8")

    expected_modules = [
        REPO_ROOT / "web" / "css" / "layout-responsive.css",
        REPO_ROOT / "web" / "css" / "components.css",
        REPO_ROOT / "web" / "css" / "portal.css",
        REPO_ROOT / "web" / "js" / "core" / "icons.js",
        REPO_ROOT / "web" / "js" / "core" / "api.js",
        REPO_ROOT / "web" / "js" / "core" / "auth-session.js",
        REPO_ROOT / "web" / "js" / "auth-login.js",
        REPO_ROOT / "web" / "js" / "portal" / "portal-main.js",
        REPO_ROOT / "web" / "js" / "portal" / "orders-tab.js",
        REPO_ROOT / "web" / "js" / "portal" / "upload-tab.js",
        REPO_ROOT / "web" / "js" / "portal" / "face-id-tab.js",
        REPO_ROOT / "web" / "js" / "portal" / "notifications-tab.js",
    ]
    for mod in expected_modules:
        assert mod.exists(), f"Missing modular asset: {mod}"


def test_hcsr04_distance_deposit_and_4_lockers_schema(db_session):
    """Verifies HC-SR04 ultrasonic distance deposit, fill_percent calculation, and 4-locker seeding."""
    from contracts.schemas import LockerInfo
    from server.main import init_database_tables

    # 1. Seeded app init ensures 4 lockers exist
    init_database_tables()
    all_lockers = lockers.list_lockers(db=db_session)
    assert len(all_lockers) >= 3

    # 2. Deposit using HC-SR04 distance_cm (e.g. 14.0 cm from 35.0 cm empty baseline -> 60% full)
    user = db_session.query(User).first()
    order = Order(
        user_id=user.id,
        tracking_number="SPX_HCSR04_001",
        expected_weight=0,
        status=OrderStatus.REGISTERED,
    )
    db_session.add(order)
    db_session.commit()

    v_res = edge.verify_package(PackageVerificationRequest(tracking_number="SPX_HCSR04_001"), db=db_session)
    assert v_res.action == "UNLOCK_DOOR"

    d_res = edge.confirm_deposit(
        DepositConfirmationRequest(
            order_id=order.id,
            locker_number=v_res.locker_number,
            distance_cm=14.0,
            empty_distance_cm=35.0,
        ),
        db=db_session,
    )
    assert d_res.success is True
    assert d_res.parcel_detected is True
    assert d_res.distance_cm == 14.0

    db_session.refresh(order)
    assert order.measured_distance_cm == 14.0

    locker_obj = db_session.query(Locker).filter(Locker.locker_number == v_res.locker_number).first()
    info = LockerInfo.model_validate(locker_obj)
    assert info.current_distance_cm == 14.0
    assert info.empty_distance_cm == 35.0
    assert info.fill_percent == 60

    # 3. Pickup resets locker distance back to empty baseline (35.0 cm)
    pickup = edge.verify_otp(OtpVerificationRequest(otp_code=d_res.otp_generated), db=db_session)
    assert pickup.valid is True
    db_session.refresh(locker_obj)
    assert locker_obj.status == LockerStatus.EMPTY
    assert locker_obj.current_distance_cm == 35.0






