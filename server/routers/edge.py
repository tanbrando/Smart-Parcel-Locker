"""
Edge Router [Person 4].
Direct endpoints invoked by Raspberry Pi 4B Edge Controller during locker operation.
"""
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, status
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
)
from server.core.config import settings
from server.core.security import generate_otp, is_otp_expired
from server.db.session import get_db
from server.db.models import Order, Locker, AccessLog
from server.services.notifier import notifier

logger = logging.getLogger("server.routers.edge")

router = APIRouter(prefix="/pi", tags=["Edge - Raspberry Pi"])


@router.post("/verify-package", response_model=PackageVerificationResponse)
def verify_package(req: PackageVerificationRequest, db: Session = Depends(get_db)):
    """
    Called when courier scans waybill barcode/QR code at the locker.
    Verifies tracking code and reserves an empty locker compartment.
    """
    tracking = req.tracking_number.strip().upper()
    order = (
        db.query(Order)
        .filter(Order.tracking_number == tracking, Order.status == OrderStatus.PENDING)
        .first()
    )

    if not order:
        return PackageVerificationResponse(
            verified=False,
            message=f"Order {tracking} not found in pending state.",
        )

    # Find available locker compartment
    available_locker = (
        db.query(Locker)
        .filter(Locker.status == LockerStatus.AVAILABLE)
        .order_id if hasattr(Locker, "order_id") else None  # safe dummy
    )
    available_locker = db.query(Locker).filter(Locker.status == LockerStatus.AVAILABLE).first()

    if not available_locker:
        return PackageVerificationResponse(
            verified=False,
            order_id=order.id,
            message="All lockers are currently occupied or in maintenance.",
        )

    # Log event
    log_entry = AccessLog(
        locker_id=available_locker.id,
        order_id=order.id,
        event_type="COURIER_VERIFY_PACKAGE",
        details=f"Tracking: {tracking} assigned to Locker {available_locker.id}",
        success=True,
    )
    db.add(log_entry)
    db.commit()

    return PackageVerificationResponse(
        verified=True,
        order_id=order.id,
        locker_id=available_locker.id,
        declared_weight_grams=order.declared_weight_grams,
        tolerance_grams=settings.WEIGHT_TOLERANCE_GRAMS,
        message=f"Authorized. Place parcel in Locker {available_locker.id}.",
    )


@router.post("/confirm-deposit", response_model=DepositConfirmationResponse)
def confirm_deposit(req: DepositConfirmationRequest, db: Session = Depends(get_db)):
    """
    Called after parcel is placed, weighed, and locker door is confirmed closed.
    Locks compartment, sets Order to DEPOSITED, generates OTP, and alerts recipient.
    """
    order = db.query(Order).filter(Order.id == req.order_id).first()
    locker = db.query(Locker).filter(Locker.id == req.locker_id).first()

    if not order or not locker:
        return DepositConfirmationResponse(
            success=False,
            order_id=req.order_id,
            locker_id=req.locker_id,
            message="Invalid order or locker reference.",
        )

    # 1. Generate 6-digit OTP
    otp_code, expires_at = generate_otp()

    # 2. Update Order
    order.status = OrderStatus.DEPOSITED
    order.locker_id = locker.id
    order.actual_weight_grams = req.final_weight_grams
    order.otp_code = otp_code
    order.otp_expires_at = expires_at

    # 3. Update Locker
    locker.status = LockerStatus.OCCUPIED
    locker.current_order_id = order.id
    locker.current_weight_grams = req.final_weight_grams

    # 4. Access Log
    log_entry = AccessLog(
        locker_id=locker.id,
        order_id=order.id,
        event_type="DEPOSIT_CONFIRMED",
        details=f"Weight: {req.final_weight_grams}g. OTP: {otp_code}",
        success=True,
    )
    db.add(log_entry)
    db.commit()

    # 5. Send Telegram notification to user
    chat_id = order.telegram_chat_id or settings.TELEGRAM_DEFAULT_CHAT_ID
    if chat_id:
        notifier.notify_parcel_deposited(
            chat_id=chat_id,
            tracking_number=order.tracking_number,
            locker_id=locker.id,
            otp_code=otp_code,
        )

    return DepositConfirmationResponse(
        success=True,
        order_id=order.id,
        locker_id=locker.id,
        message=f"Parcel stored in Locker {locker.id}. OTP dispatched to recipient.",
    )


@router.post("/verify-otp", response_model=OtpVerificationResponse)
def verify_otp(req: OtpVerificationRequest, db: Session = Depends(get_db)):
    """
    Called when recipient types OTP on 4x4 keypad.
    Unlocks locker door if code is valid and not expired.
    """
    entered_pin = req.otp_code.strip()
    query = db.query(Order).filter(
        Order.otp_code == entered_pin,
        Order.status == OrderStatus.DEPOSITED,
    )
    if req.locker_id:
        query = query.filter(Order.locker_id == req.locker_id)

    order = query.first()

    if not order:
        log_entry = AccessLog(
            locker_id=req.locker_id,
            event_type="OTP_FAILED",
            details=f"Invalid OTP entered: {entered_pin}",
            success=False,
        )
        db.add(log_entry)
        db.commit()
        return OtpVerificationResponse(
            success=False,
            message="Invalid or unrecognized OTP code.",
        )

    # Check expiration
    if order.otp_expires_at and is_otp_expired(order.otp_expires_at):
        return OtpVerificationResponse(
            success=False,
            order_id=order.id,
            locker_id=order.locker_id,
            message="OTP code has expired.",
        )

    target_locker_id = order.locker_id
    locker = db.query(Locker).filter(Locker.id == target_locker_id).first()

    # Mark retrieved
    order.status = OrderStatus.RETRIEVED
    order.otp_code = None  # Invalidate OTP once used

    # Free up locker
    if locker:
        locker.status = LockerStatus.AVAILABLE
        locker.current_order_id = None
        locker.current_weight_grams = 0.0

    # Log successful retrieval
    log_entry = AccessLog(
        locker_id=target_locker_id,
        order_id=order.id,
        event_type="OTP_SUCCESS_PICKUP",
        details=f"Parcel {order.tracking_number} collected from Locker {target_locker_id}",
        success=True,
    )
    db.add(log_entry)
    db.commit()

    # Send pickup confirmation
    chat_id = order.telegram_chat_id or settings.TELEGRAM_DEFAULT_CHAT_ID
    if chat_id:
        notifier.notify_parcel_retrieved(
            chat_id=chat_id,
            tracking_number=order.tracking_number,
            locker_id=target_locker_id or 1,
        )

    return OtpVerificationResponse(
        success=True,
        locker_id=target_locker_id,
        order_id=order.id,
        message=f"Access granted. Opening locker {target_locker_id}.",
    )

