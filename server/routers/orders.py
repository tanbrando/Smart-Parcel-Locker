"""
Orders Router [Person 4].
Handles screenshot uploads, manual parcel registration, and query endpoints.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session

from contracts.schemas import OrderCreateRequest, OrderResponse, OrderStatus
from server.db.session import get_db
from server.db.models import Order
from server.services.ocr_service import ScreenshotOcrService

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.post("/register-screenshot", response_model=OrderResponse)
async def register_order_from_screenshot(
    file: UploadFile = File(...),
    recipient_name: str = Form(...),
    recipient_phone: str = Form(...),
    telegram_chat_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """
    Parses uploaded e-commerce screenshot (Shopee/Lazada) to extract tracking code
    and registers parcel into PENDING state.
    """
    contents = await file.read()
    parsed_info = ScreenshotOcrService.parse_screenshot(contents, filename=file.filename or "")

    tracking_num = parsed_info["tracking_number"]
    existing = db.query(Order).filter(Order.tracking_number == tracking_num).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Order with tracking number {tracking_num} already exists.",
        )

    new_order = Order(
        tracking_number=tracking_num,
        recipient_name=recipient_name,
        recipient_phone=recipient_phone,
        declared_weight_grams=parsed_info.get("declared_weight_grams", 0.0),
        status=OrderStatus.PENDING,
        telegram_chat_id=telegram_chat_id,
    )
    db.add(new_order)
    db.commit()
    db.refresh(new_order)

    return new_order


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order_manual(req: OrderCreateRequest, db: Session = Depends(get_db)):
    """Manually registers an anticipated parcel arrival."""
    existing = db.query(Order).filter(Order.tracking_number == req.tracking_number).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tracking number {req.tracking_number} is already registered.",
        )

    order = Order(
        tracking_number=req.tracking_number,
        recipient_name=req.recipient_name,
        recipient_phone=req.recipient_phone,
        declared_weight_grams=req.declared_weight_grams,
        status=OrderStatus.PENDING,
        telegram_chat_id=req.telegram_chat_id,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


@router.get("", response_model=List[OrderResponse])
def list_orders(db: Session = Depends(get_db)):
    """Lists all orders in system."""
    return db.query(Order).order_by(Order.created_at.desc()).all()


@router.get("/{order_id}", response_model=OrderResponse)
def get_order_by_id(order_id: str, db: Session = Depends(get_db)):
    """Retrieves specific order details."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order

