"""
Orders Router [Person 4].
Handles screenshot uploads with user recognition (via user_id or telegram_chat_id),
manual parcel registration, and query endpoints.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request, status
from sqlalchemy.orm import Session

from contracts.schemas import (
    ScreenshotRegisterResponse,
    ScreenshotRegisterData,
    OrderResponse,
    UserCreateRequest,
    UserResponse,
    OrderStatus,
)
from server.db.session import get_db
from server.db.models import Order, User
from server.services.ocr_service import ScreenshotOcrService

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.post(
    "/register-screenshot",
    response_model=ScreenshotRegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_order_from_screenshot(
    image: UploadFile = File(...),
    telegram_chat_id: Optional[int] = Form(None),
    user_id: Optional[int] = Form(None),
    expected_weight: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    """
    Parses uploaded e-commerce screenshot (Shopee/Lazada) to extract tracking code & order code.
    Recognizes the recipient via telegram_chat_id or user_id, and registers the parcel into REGISTERED state.
    """
    # 1. User identification logic (prioritize telegram_chat_id if provided)
    user: Optional[User] = None
    if telegram_chat_id:
        user = db.query(User).filter(User.telegram_chat_id == telegram_chat_id).first()

    if not user and user_id:
        user = db.query(User).filter(User.id == user_id).first()
        if user and telegram_chat_id and not user.telegram_chat_id:
            user.telegram_chat_id = telegram_chat_id
            db.commit()

    if not user:
        if telegram_chat_id:
            # Auto-create profile for new Telegram user
            user = User(
                full_name=f"Telegram User {telegram_chat_id}",
                phone=f"09{str(abs(telegram_chat_id))[:8]}",
                phone_last4=str(abs(telegram_chat_id))[-4:],
                telegram_chat_id=telegram_chat_id,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            # Fallback to default registered user in database
            user = db.query(User).first()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No user found. Please provide a valid user_id or telegram_chat_id.",
                )

    # 2. Extract OCR metadata from image
    contents = image.file.read() if hasattr(image, "file") else image.read()
    if callable(contents):
        contents = contents()
    parsed_info = ScreenshotOcrService.parse_screenshot(contents, filename=image.filename or "")

    tracking_num = parsed_info["tracking_number"]
    order_code = parsed_info.get("order_code")
    weight = expected_weight if expected_weight is not None else parsed_info.get("expected_weight", 500)

    # 3. Check for existing order
    existing = db.query(Order).filter(Order.tracking_number == tracking_num).first()
    if existing:
        if existing.status == OrderStatus.REGISTERED:
            existing.expected_weight = weight
            existing.order_code = order_code
            existing.user_id = user.id
            db.commit()
            db.refresh(existing)
            return ScreenshotRegisterResponse(
                success=True,
                data=ScreenshotRegisterData(
                    order_id=existing.id,
                    tracking_number=existing.tracking_number,
                    order_code=existing.order_code,
                    detected_recipient=user.full_name,
                    status=existing.status,
                    message="Đơn hàng đã được cập nhật lại thông tin đăng ký!",
                ),
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Đơn hàng với mã vận đơn {tracking_num} đã ở trạng thái {existing.status.value}.",
        )

    # 4. Save new order
    new_order = Order(
        user_id=user.id,
        tracking_number=tracking_num,
        order_code=order_code,
        expected_weight=weight,
        status=OrderStatus.REGISTERED,
        screenshot_url=f"uploads/{image.filename}" if image.filename else None,
    )
    db.add(new_order)
    db.commit()
    db.refresh(new_order)

    return ScreenshotRegisterResponse(
        success=True,
        data=ScreenshotRegisterData(
            order_id=new_order.id,
            tracking_number=new_order.tracking_number,
            order_code=new_order.order_code,
            detected_recipient=user.full_name,
            status=new_order.status,
            message="Đã lưu đơn hàng. Tủ sẽ tự nhận diện khi Shipper giao đến!",
        ),
    )


@router.get("", response_model=List[OrderResponse])
def list_orders(db: Session = Depends(get_db)):
    """Lists all orders in system with user details."""
    orders = db.query(Order).order_by(Order.created_at.desc()).all()
    results = []
    for o in orders:
        ord_dict = {
            "id": o.id,
            "user_id": o.user_id,
            "locker_id": o.locker_id,
            "tracking_number": o.tracking_number,
            "order_code": o.order_code,
            "expected_weight": o.expected_weight,
            "actual_weight": o.actual_weight,
            "otp_code": o.otp_code,
            "otp_expires_at": o.otp_expires_at,
            "status": o.status,
            "screenshot_url": o.screenshot_url,
            "delivered_photo_url": o.delivered_photo_url,
            "created_at": o.created_at,
            "delivered_at": o.delivered_at,
            "collected_at": o.collected_at,
            "recipient_name": o.user.full_name if o.user else "Unknown",
            "recipient_phone": o.user.phone if o.user else "Unknown",
        }
        results.append(OrderResponse(**ord_dict))
    return results


@router.get("/users", response_model=List[UserResponse])
def list_users(db: Session = Depends(get_db)):
    """Lists registered users."""
    return db.query(User).all()


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreateRequest,
    db: Session = Depends(get_db),
):
    """Admin endpoint: Registers a new user."""
    phone_clean = payload.phone.strip()
    phone_last4 = phone_clean[-4:] if len(phone_clean) >= 4 else phone_clean
    user = User(
        full_name=payload.full_name.strip(),
        phone=phone_clean,
        phone_last4=phone_last4,
        telegram_chat_id=payload.telegram_chat_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/users/{user_id}/unlink-telegram", response_model=UserResponse)
def unlink_user_telegram(user_id: int, db: Session = Depends(get_db)):
    """Admin endpoint: Unlinks Telegram chat from a specific user."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.telegram_chat_id = None
    db.commit()
    db.refresh(user)
    return user


@router.get("/{order_id}", response_model=OrderResponse)
def get_order_by_id(order_id: int, db: Session = Depends(get_db)):
    """Retrieves specific order details."""
    o = db.query(Order).filter(Order.id == order_id).first()
    if not o:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return OrderResponse(
        id=o.id,
        user_id=o.user_id,
        locker_id=o.locker_id,
        tracking_number=o.tracking_number,
        order_code=o.order_code,
        expected_weight=o.expected_weight,
        actual_weight=o.actual_weight,
        otp_code=o.otp_code,
        otp_expires_at=o.otp_expires_at,
        status=o.status,
        screenshot_url=o.screenshot_url,
        delivered_photo_url=o.delivered_photo_url,
        created_at=o.created_at,
        delivered_at=o.delivered_at,
        collected_at=o.collected_at,
        recipient_name=o.user.full_name if o.user else None,
        recipient_phone=o.user.phone if o.user else None,
    )
