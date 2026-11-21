"""
Edge Router [Person 4].
Direct endpoints invoked by Raspberry Pi 4B Edge Controller during locker operation.
"""
import logging
import hmac
import json
import os
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Header, HTTPException, status
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
from server.services.face import extract_templates
from contracts.schemas import FaceEnrollMultiAngleRequest

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

    # Step 3: Check locker availability with Same-User Co-location & HC-SR04 clearance
    available_locker = None
    if order:
        min_free_cm = 8.0
        # Priority 1: Reuse an existing locker already holding STORED (or reserved) parcel(s) of the SAME user
        same_user_lockers = (
            db.query(Locker)
            .join(Order, Order.locker_id == Locker.id)
            .filter(
                Order.user_id == order.user_id,
                Order.id != order.id,
                Order.status.in_([OrderStatus.STORED, OrderStatus.REGISTERED]),
                Locker.status != LockerStatus.MAINTENANCE,
            )
            .order_by(Locker.locker_number.asc())
            .all()
        )
        for candidate in same_user_lockers:
            # Ensure locker still has physical clearance (HC-SR04) if measured
            if candidate.current_distance_cm is not None and candidate.current_distance_cm < min_free_cm:
                continue
            # Ensure no other user owns an active order in this locker
            other_user_order = (
                db.query(Order)
                .filter(
                    Order.locker_id == candidate.id,
                    Order.user_id != order.user_id,
                    Order.status.in_([OrderStatus.STORED, OrderStatus.REGISTERED]),
                )
                .first()
            )
            if not other_user_order:
                available_locker = candidate
                break

        # Priority 2: Assign an EMPTY locker not reserved by another user
        if not available_locker:
            empty_lockers = (
                db.query(Locker)
                .filter(Locker.status == LockerStatus.EMPTY)
                .order_by(Locker.locker_number.asc())
                .all()
            )
            for candidate in empty_lockers:
                reserved_by_other = (
                    db.query(Order)
                    .filter(
                        Order.locker_id == candidate.id,
                        Order.user_id != order.user_id,
                        Order.status == OrderStatus.REGISTERED,
                    )
                    .first()
                )
                if not reserved_by_other:
                    available_locker = candidate
                    break

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
        declared_weight_grams=order.expected_weight,
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

    # 1. Reuse existing active OTP if the same user already has STORED parcel(s) in this locker
    existing_same_user_orders = (
        db.query(Order)
        .filter(
            Order.locker_id == locker.id,
            Order.user_id == order.user_id,
            Order.status == OrderStatus.STORED,
            Order.id != order.id,
            Order.otp_code.isnot(None),
        )
        .all()
    )
    reusable_otp = None
    for prev_order in existing_same_user_orders:
        if prev_order.otp_code and not is_otp_expired(prev_order.otp_expires_at):
            reusable_otp = prev_order.otp_code
            break

    if reusable_otp:
        _, expires_at = generate_otp(length=settings.OTP_LENGTH, hours_valid=settings.OTP_VALID_HOURS)
        otp_code = reusable_otp
        # Extend expiry uniformly for all co-located parcels sharing this OTP
        for prev_order in existing_same_user_orders:
            prev_order.otp_expires_at = expires_at
    else:
        otp_code, expires_at = generate_otp(length=settings.OTP_LENGTH, hours_valid=settings.OTP_VALID_HOURS)

    # 2. HC-SR04 ultrasonic parcel detection & fallback weight check
    delta_w = req.delta_weight or 0
    empty_dist = req.empty_distance_cm if req.empty_distance_cm and req.empty_distance_cm > 0 else (locker.empty_distance_cm or 35.0)
    if req.empty_distance_cm and req.empty_distance_cm > 0:
        locker.empty_distance_cm = req.empty_distance_cm

    if req.distance_cm is not None:
        distance_cm = float(req.distance_cm)
        parcel_detected = (empty_dist - distance_cm) >= 3.0
        weight_matched = parcel_detected
        deviation_gram = 0
    else:
        distance_cm = round(max(5.0, empty_dist - 12.0), 1)
        parcel_detected = True
        expected = order.expected_weight if order.expected_weight > 0 else delta_w
        deviation_gram = abs(expected - delta_w)
        weight_matched = deviation_gram <= settings.WEIGHT_TOLERANCE_GRAMS

    # 3. Update Order
    order.status = OrderStatus.STORED
    order.locker_id = locker.id
    order.actual_weight = delta_w
    order.measured_distance_cm = distance_cm
    order.otp_code = otp_code
    order.otp_expires_at = expires_at
    order.delivered_at = datetime.now(timezone.utc)
    if req.image_base64:
        order.delivered_photo_url = req.image_base64

    # 4. Update Locker
    locker.current_weight += delta_w
    locker.current_distance_cm = distance_cm
    locker.status = LockerStatus.OCCUPIED

    # 5. Access Logs
    sensor_detail = (
        f"HC-SR04 distance: {distance_cm:.1f}cm (empty: {empty_dist:.1f}cm)"
        if req.distance_cm is not None
        else f"Delta weight: {delta_w}g"
    )
    door_log = AccessLog(
        locker_id=locker.id,
        order_id=order.id,
        action=AccessAction.DOOR_OPEN.value,
        details=f"Parcel stored in Locker #{locker.locker_number}. {sensor_detail}, OTP: {otp_code}",
    )
    db.add(door_log)

    if not parcel_detected:
        sensor_fail_log = AccessLog(
            locker_id=locker.id,
            order_id=order.id,
            action=AccessAction.WEIGHT_CHECK_FAIL.value,
            details=f"HC-SR04 did not detect parcel change: measured {distance_cm:.1f}cm vs empty {empty_dist:.1f}cm",
        )
        db.add(sensor_fail_log)

    db.commit()

    # 6. Trigger Telegram Notification
    chat_id = (order.user.telegram_chat_id if order.user else None) or settings.TELEGRAM_DEFAULT_CHAT_ID
    notifier.notify_parcel_deposited(
        chat_id=chat_id,
        tracking_number=order.tracking_number or f"ORD-{order.id}",
        locker_number=locker.locker_number,
        otp_code=otp_code,
        delta_weight=delta_w,
        image_base64=req.image_base64,
    )

    return DepositConfirmationResponse(
        success=True,
        status=OrderStatus.STORED,
        otp_generated=otp_code,
        weight_matched=weight_matched,
        deviation_gram=deviation_gram,
        distance_cm=distance_cm,
        parcel_detected=parcel_detected,
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

    # 2. Query all STORED orders matching this OTP (supports multiple co-located parcels sharing one OTP)
    matched_orders = (
        db.query(Order)
        .filter(
            Order.otp_code == entered_pin,
            Order.status == OrderStatus.STORED,
        )
        .order_by(Order.id.asc())
        .all()
    )
    order = matched_orders[0] if matched_orders else None

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

    # 3. Valid OTP -> Collect all co-located parcels sharing this OTP in the target locker
    otp_rate_limiter.reset()
    return collect_orders(order, matched_orders, db)


@router.post("/verify-face", response_model=OtpVerificationResponse)
def verify_face(payload: FaceEnrollMultiAngleRequest, db: Session = Depends(get_db),
                device_key: str = Header("", alias="X-Face-Device-Key")):
    expected_key = os.getenv("FACE_DEVICE_KEY")
    if not expected_key or not hmac.compare_digest(device_key.encode(), expected_key.encode()):
        raise HTTPException(status_code=403, detail="Face pickup device is not authorized.")
    user = db.get(User, payload.user_id)
    if not user or not user.face_auth_enabled or not user.face_registered:
        return OtpVerificationResponse(valid=False, message="Face ID is unavailable.")
    try:
        model_id, probes = extract_templates(payload.angles)
        from edge.cv.face_verify import VERIFY_SCORE, unit
        enrolled = json.loads(user.face_data_json or "{}")
        matched = all(
            enrolled[pose]["model_id"] == model_id
            and float(unit(enrolled[pose]["embedding"]) @ vector) >= VERIFY_SCORE
            for pose, vector in probes.items()
        )
    except (KeyError, TypeError, ValueError):
        matched = False
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not matched:
        return OtpVerificationResponse(valid=False, message="Five-angle verification failed.")
    orders = db.query(Order).filter(
        Order.user_id == user.id, Order.status == OrderStatus.STORED, Order.locker_id.isnot(None),
    ).order_by(Order.id).all()
    for order in orders:
        if order.locker and not db.query(Order).filter(
            Order.locker_id == order.locker_id, Order.status == OrderStatus.STORED,
            Order.user_id != user.id,
        ).first():
            return collect_orders(order, orders, db, verified_message="Face ID confirmed")
    return OtpVerificationResponse(valid=False, message="No eligible parcel for Face ID pickup.")


def collect_orders(order, matched_orders, db, verified_message="Mã chính xác"):
    target_locker = order.locker
    locker_num = target_locker.locker_number if target_locker else 1
    now_utc = datetime.now(timezone.utc)

    collected_orders = [
        o for o in matched_orders
        if (target_locker is None or o.locker_id == target_locker.id)
    ]
    collected_ids = {o.id for o in collected_orders}
    claimed = db.query(Order).filter(
        Order.id.in_(collected_ids), Order.status == OrderStatus.STORED,
    ).update({Order.status: OrderStatus.COLLECTED}, synchronize_session=False)
    if claimed != len(collected_ids):
        db.rollback()
        return OtpVerificationResponse(valid=False, message="Parcel pickup already processed.")
    total_collected_weight = 0
    collected_tracking_list = []

    for o in collected_orders:
        o.status = OrderStatus.COLLECTED
        o.collected_at = now_utc
        o.otp_code = None  # Consume OTP
        total_collected_weight += (o.actual_weight or 0)
        collected_tracking_list.append(o.tracking_number or f"ORD-{o.id}")

    # Update Locker Weight & Status
    if target_locker:
        target_locker.current_weight = max(0, target_locker.current_weight - total_collected_weight)
        other_parcels = (
            db.query(Order)
            .filter(
                Order.locker_id == target_locker.id,
                Order.status == OrderStatus.STORED,
                ~Order.id.in_(collected_ids),
            )
            .count()
        )
        if other_parcels == 0:
            target_locker.status = LockerStatus.EMPTY
            target_locker.current_weight = 0
            target_locker.current_distance_cm = target_locker.empty_distance_cm or 35.0

    # Log action
    tracking_summary = ", ".join(collected_tracking_list)
    log_entry = AccessLog(
        locker_id=target_locker.id if target_locker else None,
        order_id=order.id,
        action=AccessAction.COLLECTED.value,
        details=f"Collected {len(collected_orders)} parcel(s) [{tracking_summary}] from Locker #{locker_num}",
    )
    db.add(log_entry)
    db.commit()

    # Trigger Telegram pickup confirmation
    chat_id = (order.user.telegram_chat_id if order.user else None) or settings.TELEGRAM_DEFAULT_CHAT_ID
    notifier.notify_parcel_collected(
        chat_id=chat_id,
        tracking_number=tracking_summary,
        locker_number=locker_num,
    )

    msg = (
        f"{verified_message}. Đang mở ngăn số {locker_num} ({len(collected_orders)} kiện hàng)."
        if len(collected_orders) > 1
        else f"{verified_message}. Đang mở ngăn số {locker_num}."
    )

    return OtpVerificationResponse(
        valid=True,
        locker_number=locker_num,
        order_id=order.id,
        message=msg,
    )
