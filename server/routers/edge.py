"""
Edge Router [Person 4].
Direct endpoints invoked by Raspberry Pi 4B Edge Controller during locker operation.
"""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from contracts.schemas import (
    PackageVerificationRequest,
    PackageVerificationResponse,
    DepositConfirmationRequest,
    DepositConfirmationResponse,
    OtpVerificationRequest,
    OtpVerificationResponse,
    LockerStatus,
    OrderStatus,
    AccessAction,
)
from server.core.config import settings
from server.core.security import generate_otp, is_otp_expired, otp_rate_limiter
from server.db.session import get_db
from server.db.models import Order, Locker, AccessLog, User
from server.services.telegram import notifier

logger = logging.getLogger("server.routers.edge")

router = APIRouter(prefix="/pi", tags=["Edge - Raspberry Pi"])


@router.post("/verify-package", response_model=PackageVerificationResponse)
def verify_package(req: PackageVerificationRequest, db: Session = Depends(get_db)):
    """
    Called when courier scans waybill barcode/QR code at the locker.
    1. Looks up active REGISTERED order by tracking_number (or fallback by recipient_phone_last4).
    2. Checks available locker capacity (current_weight + ocr_weight <= max_weight).
    3. Returns decision to unlock or reject.
    """
    order = None

    # Step 1: Match by tracking_number
    if req.tracking_number:
        clean_tracking = req.tracking_number.strip().upper()
        order = (
            db.query(Order)
            .filter(Order.tracking_number == clean_tracking, Order.status == OrderStatus.REGISTERED)
            .first()
        )

    # Step 2: Fallback match by recipient_phone_last4
    if not order and req.recipient_phone_last4:
        clean_last4 = req.recipient_phone_last4.strip()
        order = (
            db.query(Order)
            .join(User, Order.user_id == User.id)
            .filter(User.phone_last4 == clean_last4, Order.status == OrderStatus.REGISTERED)
            .order_by(Order.created_at.desc())
            .first()
        )

    # Step 3: Check locker capacity
    available_locker = None
    if order:
        # Check empty lockers first
        available_locker = (
            db.query(Locker)
            .filter(
                Locker.status == LockerStatus.EMPTY,
                Locker.current_weight + req.ocr_weight <= Locker.max_weight,
            )
            .order_by(Locker.locker_number.asc())
            .first()
        )
        if not available_locker:
            # Check occupied lockers that still have remaining capacity
            available_locker = (
                db.query(Locker)
                .filter(
                    Locker.status == LockerStatus.OCCUPIED,
                    Locker.current_weight + req.ocr_weight <= Locker.max_weight,
                )
                .order_by(Locker.locker_number.asc())
                .first()
            )

    # Reject if no order found or no locker capacity
    if not order or not available_locker:
        log_entry = AccessLog(
            action=AccessAction.SHIPPER_SCAN.value,
            details=f"REJECT: Tracking={req.tracking_number}, Last4={req.recipient_phone_last4}, OCR Weight={req.ocr_weight}g. Order found={order is not None}, Locker available={available_locker is not None}",
        )
        db.add(log_entry)
        db.commit()

        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "action": "REJECT",
                "reason": "ORDER_NOT_FOUND_OR_LOCKER_FULL",
                "message": "Đơn chưa đăng ký hoặc tủ đã đầy!",
            },
        )

    # Reserve locker for order
    order.locker_id = available_locker.id
    if req.ocr_weight > 0:
        order.expected_weight = req.ocr_weight

    # Log action
    log_entry = AccessLog(
        locker_id=available_locker.id,
        order_id=order.id,
        action=AccessAction.SHIPPER_SCAN.value,
        details=f"Authorized Locker #{available_locker.locker_number} for Order #{order.id} ({order.tracking_number})",
    )
    db.add(log_entry)
    db.commit()

    return PackageVerificationResponse(
        action="UNLOCK_DOOR",
        locker_number=available_locker.locker_number,
        order_id=order.id,
        customer_name=order.user.full_name if order.user else "Khách hàng",
        max_allowed_weight=available_locker.max_weight,
        message=f"Mở ngăn số {available_locker.locker_number}",
    )


@router.post("/confirm-deposit", response_model=DepositConfirmationResponse)
def confirm_deposit(req: DepositConfirmationRequest, db: Session = Depends(get_db)):
    """
    Called after parcel is placed, weighed, and locker door is closed.
    1. Updates order: actual_weight = delta_weight, status = 'STORED', delivered_at = now().
    2. Updates locker: current_weight += delta_weight, status = 'OCCUPIED'.
    3. Generates 6-digit OTP (TTL: 72h).
    4. Triggers Telegram notification hook.
    5. Logs action to access_logs.
    """
    order = db.query(Order).filter(Order.id == req.order_id).first()
    locker = db.query(Locker).filter(Locker.locker_number == req.locker_number).first()

    if not order or not locker:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "message": "Invalid order_id or locker_number"},
        )

    # 1. Generate 6-digit OTP (TTL 72 hours)
    otp_code, expires_at = generate_otp(length=settings.OTP_LENGTH, hours_valid=settings.OTP_VALID_HOURS)

    # 2. Check weight deviation against OCR expected weight
    expected = order.expected_weight if order.expected_weight > 0 else req.delta_weight
    deviation_gram = abs(expected - req.delta_weight)
    weight_matched = deviation_gram <= settings.WEIGHT_TOLERANCE_GRAMS

    # 3. Update Order
    order.status = OrderStatus.STORED
    order.locker_id = locker.id
    order.actual_weight = req.delta_weight
    order.otp_code = otp_code
    order.otp_expires_at = expires_at
    order.delivered_at = datetime.now(timezone.utc)
    if req.image_base64:
        order.delivered_photo_url = req.image_base64

    # 4. Update Locker
    locker.current_weight += req.delta_weight
    locker.status = LockerStatus.OCCUPIED

    # 5. Access Logs
    door_log = AccessLog(
        locker_id=locker.id,
        order_id=order.id,
        action=AccessAction.DOOR_OPEN.value,
        details=f"Parcel stored in Locker #{locker.locker_number}. Delta weight: {req.delta_weight}g, OTP: {otp_code}",
    )
    db.add(door_log)

    if not weight_matched:
        weight_fail_log = AccessLog(
            locker_id=locker.id,
            order_id=order.id,
            action=AccessAction.WEIGHT_CHECK_FAIL.value,
            details=f"Weight deviation: {deviation_gram}g (Expected: {expected}g, Actual: {req.delta_weight}g) exceeds tolerance {settings.WEIGHT_TOLERANCE_GRAMS}g",
        )
        db.add(weight_fail_log)

    db.commit()

    # 6. Trigger Telegram Notification
    chat_id = (order.user.telegram_chat_id if order.user else None) or settings.TELEGRAM_DEFAULT_CHAT_ID
    notifier.notify_parcel_deposited(
        chat_id=chat_id,
        tracking_number=order.tracking_number or f"ORD-{order.id}",
        locker_number=locker.locker_number,
        otp_code=otp_code,
        delta_weight=req.delta_weight,
        image_base64=req.image_base64,
    )

    return DepositConfirmationResponse(
        success=True,
        status=OrderStatus.STORED,
        otp_generated=otp_code,
        weight_matched=weight_matched,
        deviation_gram=deviation_gram,
    )


@router.post("/verify-otp", response_model=OtpVerificationResponse)
def verify_otp(req: OtpVerificationRequest, db: Session = Depends(get_db)):
    """
    Called when recipient types OTP on 4x4 keypad.
    1. Checks rate-limiting / max 3 failed attempts before temporary lockout.
    2. Validates OTP against orders where status is 'STORED'.
    3. If valid: marks order 'COLLECTED', resets/reduces locker weight, returns locker_number.
    """
    entered_pin = req.otp_code.strip()

    # 1. Rate-limit lockout check
    if otp_rate_limiter.is_locked():
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "valid": False,
                "remaining_attempts": 0,
                "is_locked": True,
                "message": f"Hệ thống đang bị khóa tạm thời do nhập sai {settings.MAX_OTP_ATTEMPTS} lần. Vui lòng thử lại sau!",
            },
        )

    # 2. Query order
    order = (
        db.query(Order)
        .filter(
            Order.otp_code == entered_pin,
            Order.status == OrderStatus.STORED,
        )
        .first()
    )

    # Check validity & expiration
    if not order or is_otp_expired(order.otp_expires_at):
        remaining, is_locked = otp_rate_limiter.record_failure()
        log_entry = AccessLog(
            action=AccessAction.OTP_FAIL.value,
            details=f"Invalid OTP attempt '{entered_pin}'. Remaining attempts: {remaining}, Locked: {is_locked}",
        )
        db.add(log_entry)
        db.commit()

        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "valid": False,
                "remaining_attempts": remaining,
                "is_locked": is_locked,
                "message": f"Sai OTP! Còn {remaining} lần thử.",
            },
        )

    # 3. Valid OTP
    otp_rate_limiter.reset()
    target_locker = order.locker
    locker_num = target_locker.locker_number if target_locker else 1

    # Update Order
    order.status = OrderStatus.COLLECTED
    order.collected_at = datetime.now(timezone.utc)
    order.otp_code = None  # Consume OTP

    # Update Locker Weight & Status
    if target_locker:
        actual_w = order.actual_weight or 0
        target_locker.current_weight = max(0, target_locker.current_weight - actual_w)
        # Check if other stored parcels remain in locker
        other_parcels = (
            db.query(Order)
            .filter(Order.locker_id == target_locker.id, Order.status == OrderStatus.STORED, Order.id != order.id)
            .count()
        )
        if other_parcels == 0:
            target_locker.status = LockerStatus.EMPTY
            target_locker.current_weight = 0

    # Log action
    log_entry = AccessLog(
        locker_id=target_locker.id if target_locker else None,
        order_id=order.id,
        action=AccessAction.COLLECTED.value,
        details=f"Order #{order.id} ({order.tracking_number}) collected from Locker #{locker_num}",
    )
    db.add(log_entry)
    db.commit()

    # Trigger Telegram pickup confirmation
    chat_id = (order.user.telegram_chat_id if order.user else None) or settings.TELEGRAM_DEFAULT_CHAT_ID
    notifier.notify_parcel_collected(
        chat_id=chat_id,
        tracking_number=order.tracking_number or f"ORD-{order.id}",
        locker_number=locker_num,
    )

    return OtpVerificationResponse(
        valid=True,
        locker_number=locker_num,
        order_id=order.id,
        message=f"Mã chính xác. Đang mở ngăn số {locker_num}.",
    )
