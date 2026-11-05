"""
Lockers & System Monitoring Router [Person 4].
Admin endpoints for checking locker status, logs, and maintenance mode.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict
from datetime import datetime

from contracts.schemas import LockerInfo, LockerStatus
from server.db.session import get_db
from server.db.models import Locker, AccessLog

router = APIRouter(prefix="/lockers", tags=["Lockers & Admin"])


class AccessLogResponse(BaseModel):
    id: int
    locker_id: Optional[int]
    order_id: Optional[str]
    event_type: str
    details: str
    success: bool
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


@router.get("", response_model=List[LockerInfo])
def list_lockers(db: Session = Depends(get_db)):
    """Returns status and occupancy of all physical locker compartments."""
    return db.query(Locker).order_by(Locker.id.asc()).all()


@router.get("/{locker_id}", response_model=LockerInfo)
def get_locker(locker_id: int, db: Session = Depends(get_db)):
    """Retrieves specific locker status."""
    locker = db.query(Locker).filter(Locker.id == locker_id).first()
    if not locker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Locker not found")
    return locker


@router.post("/{locker_id}/maintenance", response_model=LockerInfo)
def toggle_maintenance(locker_id: int, db: Session = Depends(get_db)):
    """Toggles locker maintenance status."""
    locker = db.query(Locker).filter(Locker.id == locker_id).first()
    if not locker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Locker not found")

    if locker.status == LockerStatus.MAINTENANCE:
        locker.status = LockerStatus.AVAILABLE
    else:
        locker.status = LockerStatus.MAINTENANCE

    locker.last_maintenance = datetime.utcnow()
    db.commit()
    db.refresh(locker)
    return locker


@router.get("/admin/logs", response_model=List[AccessLogResponse])
def get_access_logs(limit: int = 50, db: Session = Depends(get_db)):
    """Fetches recent security & access audit logs."""
    return db.query(AccessLog).order_by(AccessLog.timestamp.desc()).limit(limit).all()
