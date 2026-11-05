"""
SQLAlchemy ORM Models: User, Locker, Order, and AccessLog [Person 4].
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship

from contracts.schemas import LockerStatus, OrderStatus
from server.db.session import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False)
    phone = Column(String(20), unique=True, index=True, nullable=False)
    telegram_chat_id = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    orders = relationship("Order", back_populates="recipient")


class Locker(Base):
    __tablename__ = "lockers"

    id = Column(Integer, primary_key=True, index=True)
    locker_number = Column(String(20), unique=True, nullable=False)
    status = Column(SAEnum(LockerStatus), default=LockerStatus.AVAILABLE, nullable=False)
    current_order_id = Column(
        String(36),
        ForeignKey("orders.id", use_alter=True, name="fk_locker_order_id"),
        nullable=True,
    )
    current_weight_grams = Column(Float, default=0.0)
    max_weight_capacity_grams = Column(Float, default=5000.0)
    last_maintenance = Column(DateTime, default=datetime.utcnow)

    orders = relationship("Order", foreign_keys="Order.locker_id", back_populates="locker")
    logs = relationship("AccessLog", back_populates="locker")


class Order(Base):
    __tablename__ = "orders"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tracking_number = Column(String(50), unique=True, index=True, nullable=False)
    recipient_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    recipient_name = Column(String(100), nullable=False)
    recipient_phone = Column(String(20), index=True, nullable=False)
    declared_weight_grams = Column(Float, default=0.0)
    actual_weight_grams = Column(Float, nullable=True)
    status = Column(SAEnum(OrderStatus), default=OrderStatus.PENDING, nullable=False)
    locker_id = Column(Integer, ForeignKey("lockers.id"), nullable=True)
    otp_code = Column(String(10), nullable=True, index=True)
    otp_expires_at = Column(DateTime, nullable=True)
    telegram_chat_id = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    recipient = relationship("User", back_populates="orders")
    locker = relationship("Locker", foreign_keys=[locker_id], back_populates="orders")
    logs = relationship("AccessLog", back_populates="order")


class AccessLog(Base):
    __tablename__ = "access_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    locker_id = Column(Integer, ForeignKey("lockers.id"), nullable=True)
    order_id = Column(String(36), ForeignKey("orders.id"), nullable=True)
    event_type = Column(String(50), nullable=False)  # VERIFY_PACKAGE, DEPOSIT, OTP_TRY, OTP_SUCCESS
    details = Column(String(255), default="")
    success = Column(Boolean, default=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

    locker = relationship("Locker", back_populates="logs")
    order = relationship("Order", back_populates="logs")
