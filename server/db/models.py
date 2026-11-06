"""
SQLAlchemy ORM Models: User, Locker, Order, and AccessLog [Person 4].
Strict schema implementation adhering to the IoT Smart Parcel Locker specification.
"""
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Integer,
    BigInteger,
    Text,
    DateTime,
    ForeignKey,
    Enum as SAEnum,
)
from sqlalchemy.orm import relationship

from contracts.schemas import LockerStatus, OrderStatus
from server.db.session import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    full_name = Column(String(100), nullable=False)
    phone = Column(String(15), unique=True, index=True, nullable=False)
    phone_last4 = Column(String(4), index=True, nullable=False)
    telegram_chat_id = Column(BigInteger, unique=True, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    orders = relationship("Order", back_populates="user", cascade="all, delete-orphan")


class Locker(Base):
    __tablename__ = "lockers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    locker_number = Column(Integer, unique=True, index=True, nullable=False)
    current_weight = Column(Integer, default=0, nullable=False)
    max_weight = Column(Integer, default=5000, nullable=False)
    status = Column(SAEnum(LockerStatus), default=LockerStatus.EMPTY, nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    orders = relationship("Order", back_populates="locker")
    logs = relationship("AccessLog", back_populates="locker")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    locker_id = Column(Integer, ForeignKey("lockers.id", ondelete="SET NULL"), nullable=True)
    tracking_number = Column(String(50), unique=True, index=True, nullable=True)
    order_code = Column(String(50), nullable=True)
    expected_weight = Column(Integer, default=0, nullable=False)
    actual_weight = Column(Integer, nullable=True)
    otp_code = Column(String(6), index=True, nullable=True)
    otp_expires_at = Column(DateTime, nullable=True)
    status = Column(SAEnum(OrderStatus), default=OrderStatus.REGISTERED, nullable=False)
    screenshot_url = Column(Text, nullable=True)
    delivered_photo_url = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    delivered_at = Column(DateTime, nullable=True)
    collected_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="orders")
    locker = relationship("Locker", back_populates="orders")
    logs = relationship("AccessLog", back_populates="order")


class AccessLog(Base):
    __tablename__ = "access_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    locker_id = Column(Integer, ForeignKey("lockers.id", ondelete="SET NULL"), nullable=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(50), nullable=False)  # SHIPPER_SCAN, DOOR_OPEN, WEIGHT_CHECK_FAIL, OTP_FAIL, COLLECTED
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    locker = relationship("Locker", back_populates="logs")
    order = relationship("Order", back_populates="logs")
