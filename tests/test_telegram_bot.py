"""
Telegram Chatbot Service & Conflict Guard Tests [Person 4].
Tests Account Rebinding Protection, MediaGroup/Album handling,
utility commands (/orders, /check, /lockers, /profile, /unlink, /help),
and direct parcel screenshot ingestion.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from contracts.schemas import OrderStatus, LockerStatus
from server.db.session import Base
from server.db.models import User, Locker, Order
from server.services.telegram_bot import process_simulated_command
from server.routers import orders as orders_router

test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    # Monkeypatch SessionLocal in telegram_bot to use in-memory engine
    monkeypatch.setattr("server.services.telegram_bot.SessionLocal", TestingSessionLocal)

    db = TestingSessionLocal()
    # Seed User 1 (linked to chat 123456789)
    u1 = User(id=1, full_name="Nguyễn Minh Tấn", phone="0912343456", phone_last4="3456", telegram_chat_id=123456789)
    # Seed User 2 (unlinked)
    u2 = User(id=2, full_name="Trần Thị Hoa", phone="0987654321", phone_last4="4321", telegram_chat_id=None)
    # Seed User 3 (unlinked)
    u3 = User(id=3, full_name="Lê Văn Cường", phone="0933445566", phone_last4="5566", telegram_chat_id=None)
    db.add_all([u1, u2, u3])

    # Seed Lockers
    l1 = Locker(id=1, locker_number=1, current_weight=0, max_weight=5000, status=LockerStatus.EMPTY)
    l2 = Locker(id=2, locker_number=2, current_weight=0, max_weight=5000, status=LockerStatus.EMPTY)
    l3 = Locker(id=3, locker_number=3, current_weight=0, max_weight=5000, status=LockerStatus.EMPTY)
    db.add_all([l1, l2, l3])

    db.commit()
    db.close()
    yield


def test_start_unlinked_prompts_admin():
    # Chat 999999 has no account and passes no user_id
    res = process_simulated_command(chat_id=999999, text="/start")
    assert res["success"] is False
    assert "chưa được Quản trị viên cấp phép" in res["response"]
    assert "liên hệ Admin" in res["response"]


def test_rebinding_conflict_case_1():
    """Trường hợp 1: User #1 đã được liên kết với chat 123456789, chat 999999 cố tình /link 1."""
    res = process_simulated_command(chat_id=999999, text="/link 1")
    assert res["success"] is False
    assert "Tài khoản này đã được liên kết với một Telegram khác" in res["response"]


def test_rebinding_conflict_case_2():
    """Trường hợp 2: Chat 123456789 đã liên kết với User #1, nhưng lại gõ /link 2 mà chưa /unlink."""
    res = process_simulated_command(chat_id=123456789, text="/link 2")
    assert res["success"] is False
    assert "hiện đang liên kết với tài khoản #1" in res["response"]
    assert "Vui lòng gõ lệnh /unlink" in res["response"]


def test_unlink_and_rebind_success():
    """Kiểm tra /unlink thiết bị thành công và liên kết sang tài khoản mới."""
    # 1. Unlink current chat 123456789
    res_unlink = process_simulated_command(chat_id=123456789, text="/unlink")
    assert res_unlink["success"] is True
    assert "gỡ liên kết" in res_unlink["response"]

    # 2. Now link to User #2
    res_link = process_simulated_command(chat_id=123456789, text="/link 2")
    assert res_link["success"] is True
    assert "KÍCH HOẠT TÀI KHOẢN THÀNH CÔNG" in res_link["response"]
    assert "Trần Thị Hoa" in res_link["response"]


def test_start_with_deep_link_id():
    """Kiểm tra /start <user_id> kích hoạt tài khoản ngay lập tức."""
    # Chat 777777 activates User #3
    res = process_simulated_command(chat_id=777777, text="/start 3")
    assert res["success"] is True
    assert "Lê Văn Cường" in res["response"]
    assert "#3" in res["response"]


def test_photo_upload_when_unlinked():
    """Gửi ảnh khi chưa kích hoạt tài khoản -> Bị từ chối."""
    res = process_simulated_command(
        chat_id=888888,
        text="",
        photo_bytes=b"fake-image-bytes",
        filename="test.png",
    )
    assert res["success"] is False
    assert "chưa kích hoạt tài khoản" in res["response"]


def test_photo_upload_when_linked():
    """Gửi ảnh đơn hàng khi đã kích hoạt -> OCR thành công và tạo đơn REGISTERED."""
    res = process_simulated_command(
        chat_id=123456789,  # Linked to User #1 (Nguyễn Minh Tấn)
        text="",
        photo_bytes=b"fake-shopee-screenshot-data",
        filename="SPXVN048291048_screenshot.png",
    )
    assert res["success"] is True
    assert "ĐÃ TIẾP NHẬN ĐƠN HÀNG THÀNH CÔNG" in res["response"]
    assert "SPXVN048291048" in res["response"]
    assert "Nguyễn Minh Tấn" in res["response"]

    # Verify DB Order record
    db = TestingSessionLocal()
    order = db.query(Order).filter(Order.tracking_number == "SPXVN048291048").first()
    assert order is not None
    assert order.user_id == 1
    assert order.status == OrderStatus.REGISTERED
    assert order.expected_weight in (500, 520)
    db.close()


def test_album_media_group_deduplication():
    """Gửi Album ảnh (Media Group) -> Chỉ xử lý ảnh đầu tiên, ảnh thứ 2 bị bỏ qua để tránh trùng."""
    # Photo 1 of album
    res1 = process_simulated_command(
        chat_id=123456789,
        text="",
        photo_bytes=b"photo1",
        filename="album_photo_1.png",
        media_group_id="group_album_999",
    )
    assert res1["success"] is True

    # Photo 2 of same album within 60s
    res2 = process_simulated_command(
        chat_id=123456789,
        text="",
        photo_bytes=b"photo2",
        filename="album_photo_2.png",
        media_group_id="group_album_999",
    )
    assert res2["success"] is False
    assert res2["response"] == "duplicate_album_ignored"


def test_utility_commands_orders_check_lockers_profile():
    # 1. Setup orders for User #1
    db = TestingSessionLocal()
    o_stored = Order(
        user_id=1,
        locker_id=1,
        tracking_number="SPX_STORED_1",
        order_code="COD123",
        expected_weight=500,
        actual_weight=490,
        otp_code="889900",
        status=OrderStatus.STORED,
    )
    o_pending = Order(
        user_id=1,
        tracking_number="SPX_PENDING_2",
        order_code="COD456",
        expected_weight=300,
        status=OrderStatus.REGISTERED,
    )
    db.add_all([o_stored, o_pending])
    db.commit()
    db.close()

    # Test /orders: must show OTP and Locker # for stored orders
    res_orders = process_simulated_command(chat_id=123456789, text="/orders")
    assert res_orders["success"] is True
    assert "SPX_STORED_1" in res_orders["response"]
    assert "889900" in res_orders["response"]
    assert "#1" in res_orders["response"]
    assert "SPX_PENDING_2" in res_orders["response"]

    # Test /check <tracking_number>
    res_check = process_simulated_command(chat_id=123456789, text="/check SPX_STORED_1")
    assert res_check["success"] is True
    assert "CHI TIẾT BƯU KIỆN" in res_check["response"]
    assert "889900" in res_check["response"]

    # Test /lockers
    res_lockers = process_simulated_command(chat_id=123456789, text="/lockers")
    assert res_lockers["success"] is True
    assert "TÌNH TRẠNG TỦ THÔNG MINH" in res_lockers["response"]

    # Test /profile
    res_profile = process_simulated_command(chat_id=123456789, text="/profile")
    assert res_profile["success"] is True
    assert "Nguyễn Minh Tấn" in res_profile["response"]
    assert "123456789" in res_profile["response"]

    # Test /help
    res_help = process_simulated_command(chat_id=123456789, text="/help")
    assert res_help["success"] is True
    assert "HƯỚNG DẪN SỬ DỤNG" in res_help["response"]


def test_admin_unlink_user_endpoint():
    db = TestingSessionLocal()
    user = db.query(User).filter(User.id == 1).first()
    assert user.telegram_chat_id == 123456789

    # Admin calls unlink endpoint
    res = orders_router.unlink_user_telegram(user_id=1, db=db)
    assert res.telegram_chat_id is None

    db.refresh(user)
    assert user.telegram_chat_id is None
    db.close()


def test_telegram_service_facade_and_templates():
    from server.services.telegram import telegram_service, TelegramTemplates, notifier

    # Verify templates
    deposit_msg = TelegramTemplates.parcel_deposited("SPXVN999", 2, 600, "998877", 72)
    assert "SPXVN999" in deposit_msg
    assert "998877" in deposit_msg
    assert "Số 2" in deposit_msg

    collected_msg = TelegramTemplates.parcel_collected("SPXVN999", 2)
    assert "NHẬN HÀNG THÀNH CÔNG" in collected_msg

    # Verify telegram_service facade
    assert telegram_service.templates is TelegramTemplates
    assert telegram_service.notifier is notifier

    # Verify notifier mock run
    assert notifier.notify_parcel_deposited(None, "SPXVN999", 2, "998877", 600) is True
    assert notifier.notify_parcel_collected(None, "SPXVN999", 2) is True

