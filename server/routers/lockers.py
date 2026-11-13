"""
Lockers & System Monitoring Router [Person 4].
Admin endpoints for checking locker status, logs, and maintenance mode.
"""
from typing import List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from contracts.schemas import LockerInfo, LockerStatus, AccessLogResponse
from server.db.session import get_db
from server.db.models import Locker, AccessLog

router = APIRouter(prefix="/lockers", tags=["Lockers & Admin"])


@router.get("", response_model=List[LockerInfo])
def list_lockers(db: Session = Depends(get_db)):
    """Returns status and occupancy of all physical locker compartments."""
    return db.query(Locker).order_by(Locker.locker_number.asc()).all()


@router.get("/logs", response_model=List[AccessLogResponse])
@router.get("/admin/logs", response_model=List[AccessLogResponse])
def get_access_logs(limit: int = 50, db: Session = Depends(get_db)):
    """Fetches recent security & access audit logs."""
    return db.query(AccessLog).order_by(AccessLog.created_at.desc()).limit(limit).all()


@router.get("/{locker_number}", response_model=LockerInfo)
def get_locker(locker_number: int, db: Session = Depends(get_db)):
    """Retrieves specific locker status by locker number."""
    locker = db.query(Locker).filter(Locker.locker_number == locker_number).first()
    if not locker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Locker not found")
    return locker


@router.patch("/{locker_number}/maintenance", response_model=LockerInfo)
@router.post("/{locker_number}/maintenance", response_model=LockerInfo)
def toggle_maintenance(locker_number: int, db: Session = Depends(get_db)):
    """Toggles locker maintenance status."""
    locker = db.query(Locker).filter(Locker.locker_number == locker_number).first()
    if not locker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Locker not found")

    if locker.status == LockerStatus.MAINTENANCE:
        locker.status = LockerStatus.EMPTY
    else:
        locker.status = LockerStatus.MAINTENANCE

    locker.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(locker)
    return locker
