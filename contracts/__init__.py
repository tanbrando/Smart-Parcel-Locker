"""Contracts package defining shared schemas, models, and mock data for Smart Parcel Locker."""
from contracts.schemas import (
    LockerStatus,
    OrderStatus,
    SystemState,
    ScanResult,
    WeightMeasurement,
    PackageVerificationRequest,
    PackageVerificationResponse,
    DepositConfirmationRequest,
    DepositConfirmationResponse,
    OtpVerificationRequest,
    OtpVerificationResponse,
    OrderCreateRequest,
    OrderResponse,
    LockerInfo,
)

__all__ = [
    "LockerStatus",
    "OrderStatus",
    "SystemState",
    "ScanResult",
    "WeightMeasurement",
    "PackageVerificationRequest",
    "PackageVerificationResponse",
    "DepositConfirmationRequest",
    "DepositConfirmationResponse",
    "OtpVerificationRequest",
    "OtpVerificationResponse",
    "OrderCreateRequest",
    "OrderResponse",
    "LockerInfo",
]

