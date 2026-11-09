"""
Telegram Interactive Command & Media Handlers [Person 4].
Pure business logic for account linking, order queries, album deduplication, and photo ingestion.
"""
import time
import logging
import sys
from typing import Optional, Tuple, Dict, Any
from sqlalchemy.orm import Session

from contracts.schemas import OrderStatus, LockerStatus
from server.core.config import settings
from server.db.session import SessionLocal
from server.db.models import User, Order, Locker
from server.services.ocr_service import ScreenshotOcrService
from server.services.telegram.templates import TelegramTemplates

logger = logging.getLogger("server.services.telegram.handlers")

# Album deduplication cache: media_group_id -> timestamp (60s TTL)
PROCESSED_MEDIA_GROUPS: Dict[str, float] = {}


def _cleanup_old_media_groups():
    now = time.time()
    expired = [k for k, v in PROCESSED_MEDIA_GROUPS.items() if now - v > 60.0]
    for k in expired:
        PROCESSED_MEDIA_GROUPS.pop(k, None)


def _get_db_session() -> Session:
    """Helper to obtain DB session, respecting monkeypatching in test suites."""
    tb = sys.modules.get("server.services.telegram_bot")
    if tb and hasattr(tb, "SessionLocal") and tb.SessionLocal is not SessionLocal:
        return tb.SessionLocal()
    return SessionLocal()


# ============================================================================
# Core Business Logic (Independent of telegram library, 100% testable)
# ============================================================================

def link_user_to_chat(db: Session, user_id: int, chat_id: int) -> Tuple[bool, str]:
    """
    Links a user account to a Telegram chat with conflict protection:
    - Case 1: Target user already bound to another chat -> Reject.
    - Case 2: Current chat already bound to another user -> Reject, request /unlink first.
    """
    # Case 2 Check: Is this Telegram device/chat already linked to another user?
    existing_for_chat = db.query(User).filter(User.telegram_chat_id == chat_id).first()
    if existing_for_chat and existing_for_chat.id != user_id:
        return False, TelegramTemplates.rebinding_conflict_device_already_linked(
            existing_for_chat.id, existing_for_chat.full_name
        )

    # Case 1 Check: Does target user exist, and are they already bound to another chat?
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        return False, TelegramTemplates.user_not_found(user_id)

    if target_user.telegram_chat_id and target_user.telegram_chat_id != chat_id:
        return False, TelegramTemplates.rebinding_conflict_account_already_taken()

    # Valid link
    target_user.telegram_chat_id = chat_id
    db.commit()
    db.refresh(target_user)

    return True, TelegramTemplates.activation_success(
        target_user.id, target_user.full_name, target_user.phone
    )


def unlink_chat(db: Session, chat_id: int) -> Tuple[bool, str]:
    """Unbinds the current Telegram chat from any user account."""
    user = db.query(User).filter(User.telegram_chat_id == chat_id).first()
    if not user:
        return False, TelegramTemplates.unlink_unlinked_device()

    user_id = user.id
    user_name = user.full_name
    user.telegram_chat_id = None
    db.commit()

    return True, TelegramTemplates.unlink_success(user_id, user_name)


def get_user_orders_summary(db: Session, chat_id: int) -> str:
    """Returns categorized summary of parcels belonging to this user."""
    user = db.query(User).filter(User.telegram_chat_id == chat_id).first()
    if not user:
        return TelegramTemplates.unactivated_prompt()

    orders = db.query(Order).filter(Order.user_id == user.id).order_by(Order.created_at.desc()).all()
    if not orders:
        return TelegramTemplates.no_orders()

    pending = [o for o in orders if o.status == OrderStatus.REGISTERED]
    stored = [o for o in orders if o.status == OrderStatus.STORED]
    collected = [o for o in orders if o.status == OrderStatus.COLLECTED]

    return TelegramTemplates.orders_summary(user.full_name, stored, pending, collected)


def check_order_detail(db: Session, chat_id: int, tracking_number: str) -> str:
    """Looks up specific parcel tracking number."""
    user = db.query(User).filter(User.telegram_chat_id == chat_id).first()
    if not user:
        return "❌ Bạn chưa kích hoạt tài khoản. Vui lòng nhập `/link <user_id>` trước."

    clean_code = tracking_number.strip().upper()
    order = (
        db.query(Order)
        .filter(Order.user_id == user.id, Order.tracking_number.ilike(f"%{clean_code}%"))
        .first()
    )

    if not order:
        return TelegramTemplates.order_not_found(clean_code)

    locker_info = f"Ngăn tủ số #{order.locker.locker_number}" if order.locker else "Chưa xếp tủ"
    otp_info = f"`{order.otp_code}`" if order.otp_code else "Chưa có (Chờ shipper giao)"
    created_at_str = order.created_at.strftime("%H:%M %d/%m/%Y") if order.created_at else "-"

    return TelegramTemplates.order_detail(
        tracking_number=order.tracking_number,
        order_code=order.order_code,
        status_value=order.status.value,
        locker_info=locker_info,
        otp_info=otp_info,
        expected_weight=order.expected_weight,
        actual_weight=order.actual_weight,
        created_at_str=created_at_str,
    )


def get_lockers_summary(db: Session) -> str:
    """Returns locker occupancy summary."""
    lockers = db.query(Locker).order_by(Locker.locker_number.asc()).all()
    empty_count = sum(1 for l in lockers if l.status == LockerStatus.EMPTY)
    total = len(lockers)

    lines = []
    for l in lockers:
        pct = int((l.current_weight / l.max_weight) * 100) if l.max_weight > 0 else 0
        lines.append(f"• Ngăn #{l.locker_number}: *{l.status.value}* ({l.current_weight}g/{l.max_weight}g - {pct}%)")

    return TelegramTemplates.lockers_summary(empty_count, total, lines)


def get_user_profile(db: Session, chat_id: int) -> str:
    """Returns user profile information."""
    user = db.query(User).filter(User.telegram_chat_id == chat_id).first()
    if not user:
        return "❌ Bạn chưa liên kết tài khoản nào. Hãy liên hệ Admin nhận User ID và gõ `/link <user_id>`."

    return TelegramTemplates.user_profile(
        user_id=user.id,
        full_name=user.full_name,
        phone=user.phone,
        phone_last4=user.phone_last4,
        chat_id=user.telegram_chat_id,
    )


def get_help_message() -> str:
    """Returns general help and usage guide."""
    return TelegramTemplates.help_message()


def process_incoming_photo(
    db: Session,
    chat_id: int,
    photo_bytes: bytes,
    filename: str = "",
    media_group_id: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Processes incoming photo or document image from Telegram:
    - Checks user activation.
    - Deduplicates albums (media_group_id).
    - OCR extracts tracking and registers order.
    """
    _cleanup_old_media_groups()

    # 1. Media Group / Album deduplication
    if media_group_id:
        if media_group_id in PROCESSED_MEDIA_GROUPS:
            logger.info("Ignoring duplicate photo in album %s", media_group_id)
            return False, "duplicate_album_ignored"
        PROCESSED_MEDIA_GROUPS[media_group_id] = time.time()

    # 2. Check user activation
    user = db.query(User).filter(User.telegram_chat_id == chat_id).first()
    if not user:
        return False, TelegramTemplates.photo_upload_unlinked()

    # 3. Parse OCR from image bytes
    parsed_info = ScreenshotOcrService.parse_screenshot(photo_bytes, filename=filename)
    tracking_num = parsed_info["tracking_number"]
    order_code = parsed_info.get("order_code")
    weight = parsed_info.get("expected_weight", 520)

    # 4. Check existing order
    existing = db.query(Order).filter(Order.tracking_number == tracking_num).first()
    if existing:
        if existing.status == OrderStatus.REGISTERED:
            existing.expected_weight = weight
            existing.order_code = order_code
            existing.user_id = user.id
            db.commit()
            return True, TelegramTemplates.order_updated_success(
                existing.tracking_number, existing.order_code, user.full_name, weight
            )
        return False, f"⚠️ Đơn hàng với mã vận đơn `{tracking_num}` đã ở trạng thái *{existing.status.value}*."

    # 5. Create new order
    new_order = Order(
        user_id=user.id,
        tracking_number=tracking_num,
        order_code=order_code,
        expected_weight=weight,
        status=OrderStatus.REGISTERED,
    )
    db.add(new_order)
    db.commit()
    db.refresh(new_order)

    return True, TelegramTemplates.order_registered_success(
        new_order.tracking_number, new_order.order_code, user.full_name, new_order.expected_weight
    )


def process_simulated_command(
    chat_id: int,
    text: str,
    photo_bytes: Optional[bytes] = None,
    filename: str = "",
    media_group_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Unified dispatcher for simulation endpoints and automated unit tests."""
    db = _get_db_session()
    try:
        # 1. Photo handling
        if photo_bytes is not None:
            success, msg = process_incoming_photo(db, chat_id, photo_bytes, filename, media_group_id)
            return {"success": success, "response": msg}

        # 2. Text command handling
        cmd = text.strip()
        parts = cmd.split(maxsplit=1)
        base_cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if base_cmd == "/start":
            if arg:
                try:
                    uid = int(arg)
                    success, msg = link_user_to_chat(db, uid, chat_id)
                    return {"success": success, "response": msg}
                except ValueError:
                    return {"success": False, "response": "❌ Mã User ID phải là số nguyên (ví dụ: `/start 3`)."}
            # No argument: check if already linked
            user = db.query(User).filter(User.telegram_chat_id == chat_id).first()
            if user:
                return {
                    "success": True,
                    "response": TelegramTemplates.start_already_linked(user.full_name, user.id),
                }
            return {
                "success": False,
                "response": TelegramTemplates.start_unlinked_prompt(),
            }

        elif base_cmd == "/link":
            if not arg:
                return {"success": False, "response": "⚠️ Vui lòng nhập kèm User ID (ví dụ: `/link 3`)."}
            try:
                uid = int(arg)
                success, msg = link_user_to_chat(db, uid, chat_id)
                return {"success": success, "response": msg}
            except ValueError:
                return {"success": False, "response": "❌ Mã User ID phải là số nguyên (ví dụ: `/link 3`)."}

        elif base_cmd == "/unlink":
            success, msg = unlink_chat(db, chat_id)
            return {"success": success, "response": msg}

        elif base_cmd in ("/orders", "/status"):
            msg = get_user_orders_summary(db, chat_id)
            return {"success": True, "response": msg}

        elif base_cmd == "/check":
            if not arg:
                return {"success": False, "response": "⚠️ Vui lòng nhập mã vận đơn cần tra cứu (ví dụ: `/check SPXVN048291048`)."}
            msg = check_order_detail(db, chat_id, arg)
            return {"success": True, "response": msg}

        elif base_cmd == "/lockers":
            msg = get_lockers_summary(db)
            return {"success": True, "response": msg}

        elif base_cmd == "/profile":
            msg = get_user_profile(db, chat_id)
            return {"success": True, "response": msg}

        elif base_cmd == "/help":
            return {"success": True, "response": get_help_message()}

        else:
            return {
                "success": False,
                "response": TelegramTemplates.invalid_command(),
            }
    finally:
        db.close()

