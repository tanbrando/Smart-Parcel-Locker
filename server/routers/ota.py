"""
OTA Software Update Router [Admin & Raspberry Pi OTA Agent].
Supports ZIP release upload, SHA-256 + HMAC signing, update/rollback jobs,
and HTTP polling by the independent Raspberry Pi OTA Agent.
"""
import hmac
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from server.core.security import parse_session_token
from server.db.models import AccessLog, SoftwareRelease, UpdateJob, User
from server.db.session import get_db
from server.services.ota_service import (
    DEFAULT_OTA_STORAGE_DIR,
    MAX_OTA_ZIP_BYTES,
    SEMVER_RE,
    compute_file_sha256,
    get_current_app_version,
    get_ota_agent_key,
    sign_release_hash,
    validate_zip_archive,
)

logger = logging.getLogger("server.routers.ota")
router = APIRouter(prefix="/ota", tags=["OTA Software Update"])

ACTIVE_JOB_STATUSES = {
    "PENDING",
    "DOWNLOADING",
    "VERIFYING",
    "INSTALLING",
    "RESTARTING",
    "HEALTH_CHECK",
}
TERMINAL_JOB_STATUSES = {"SUCCESS", "FAILED", "ROLLED_BACK", "DEVICE_OFFLINE"}


# ==========================================
# Pydantic Schemas
# ==========================================

class TriggerUpdateRequest(BaseModel):
    release_id: int = Field(..., description="ID của bản release cần cập nhật")


class TriggerRollbackRequest(BaseModel):
    target_version: Optional[str] = Field(
        None,
        description="Phiên bản muốn rollback về (để trống sẽ về bản trước gần nhất)",
    )


class AgentJobStatusUpdate(BaseModel):
    status: str = Field(..., description="Trạng thái job (DOWNLOADING, VERIFYING, ..., SUCCESS, FAILED, ROLLED_BACK)")
    progress: int = Field(0, ge=0, le=100)
    message: str = Field("")


# ==========================================
# Auth Helpers
# ==========================================

def require_admin(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> User:
    """Validates Bearer token belongs to an ADMIN account."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Vui lòng đăng nhập bằng tài khoản Quản trị viên (Admin).",
        )
    parsed = parse_session_token(authorization[7:].strip())
    if not parsed:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phiên đăng nhập không hợp lệ hoặc đã hết hạn.",
        )
    user_id, role = parsed
    if role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ Quản trị viên (ADMIN) mới có quyền cập nhật phần mềm OTA.",
        )
    user = db.query(User).filter(User.id == user_id).first()
    if not user or user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản không có quyền Quản trị viên.",
        )
    return user


def require_ota_agent(
    agent_key: str = Header("", alias="X-OTA-Agent-Key"),
) -> bool:
    expected = get_ota_agent_key()
    if not expected or not hmac.compare_digest(agent_key.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="OTA Agent không được cấp quyền (sai X-OTA-Agent-Key).",
        )
    return True


def _serialize_release(r: SoftwareRelease) -> dict:
    return {
        "id": r.id,
        "version": r.version,
        "filename": r.filename,
        "file_size": r.file_size,
        "sha256": r.sha256,
        "signature": r.signature,
        "changelog": r.changelog,
        "created_by": r.created_by,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _serialize_job(j: UpdateJob) -> dict:
    try:
        logs = json.loads(j.logs_json or "[]")
    except Exception:
        logs = []
    return {
        "id": j.id,
        "release_id": j.release_id,
        "action": j.action,
        "target_version": j.target_version,
        "previous_version": j.previous_version,
        "status": j.status,
        "progress": j.progress,
        "message": j.message,
        "logs": logs,
        "started_at": j.started_at.isoformat() if j.started_at else None,
        "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        "created_at": j.created_at.isoformat() if j.created_at else None,
    }


def _append_job_log(job: UpdateJob, status_val: str, message: str) -> None:
    try:
        logs = json.loads(job.logs_json or "[]")
        if not isinstance(logs, list):
            logs = []
    except Exception:
        logs = []
    logs.append(
        {
            "time": datetime.now(timezone.utc).isoformat(),
            "status": status_val,
            "message": message,
        }
    )
    job.logs_json = json.dumps(logs, ensure_ascii=False)


# ==========================================
# Admin Endpoints
# ==========================================

@router.get("/status")
def get_ota_status(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Returns current running version, active job (if any), and summary stats."""
    active_job = (
        db.query(UpdateJob)
        .filter(UpdateJob.status.in_(ACTIVE_JOB_STATUSES))
        .order_by(UpdateJob.id.desc())
        .first()
    )
    latest_job = db.query(UpdateJob).order_by(UpdateJob.id.desc()).first()
    total_releases = db.query(SoftwareRelease).count()

    return {
        "current_version": get_current_app_version(),
        "total_releases": total_releases,
        "active_job": _serialize_job(active_job) if active_job else None,
        "latest_job": _serialize_job(latest_job) if latest_job else None,
    }


@router.get("/releases")
def list_releases(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    releases = db.query(SoftwareRelease).order_by(SoftwareRelease.created_at.desc()).all()
    return [_serialize_release(r) for r in releases]


@router.post("/releases", status_code=status.HTTP_201_CREATED)
async def upload_release(
    version: str = Form(...),
    changelog: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Admin uploads a release ZIP package, validates it, computes SHA-256 and signs it."""
    clean_version = version.strip().lstrip("vV")
    if not SEMVER_RE.match(clean_version):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phiên bản phải theo định dạng SemVer (ví dụ: 1.1.0 hoặc 1.2.0-beta.1).",
        )

    existing = db.query(SoftwareRelease).filter(SoftwareRelease.version == clean_version).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Phiên bản {clean_version} đã tồn tại. Vui lòng tăng số phiên bản.",
        )

    DEFAULT_OTA_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    safe_filename = f"release-v{clean_version}.zip"
    target_path = DEFAULT_OTA_STORAGE_DIR / safe_filename

    total_written = 0
    try:
        with target_path.open("wb") as out:
            while True:
                chunk = await file.read(65536)
                if not chunk:
                    break
                total_written += len(chunk)
                if total_written > MAX_OTA_ZIP_BYTES:
                    out.close()
                    target_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File ZIP vượt quá giới hạn {MAX_OTA_ZIP_BYTES // (1024 * 1024)} MB.",
                    )
                out.write(chunk)
    except HTTPException:
        raise
    except Exception as exc:
        target_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Không thể lưu file tải lên: {exc}") from exc

    ok, reason, _manifest = validate_zip_archive(target_path, expected_version=clean_version)
    if not ok:
        target_path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)

    sha256_hex = compute_file_sha256(target_path)
    signature = sign_release_hash(sha256_hex, clean_version)

    release = SoftwareRelease(
        version=clean_version,
        filename=safe_filename,
        file_path=str(target_path),
        file_size=total_written,
        sha256=sha256_hex,
        signature=signature,
        changelog=changelog.strip(),
        created_by=admin.full_name or admin.phone,
    )
    db.add(release)
    db.add(
        AccessLog(
            action="OTA_UPLOAD",
            details=f"Admin {admin.full_name} tải lên gói OTA v{clean_version} (sha256={sha256_hex[:12]}...)",
        )
    )
    db.commit()
    db.refresh(release)
    logger.info("Uploaded OTA release v%s (%d bytes)", clean_version, total_written)
    return _serialize_release(release)


@router.delete("/releases/{release_id}")
def delete_release(
    release_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    release = db.query(SoftwareRelease).filter(SoftwareRelease.id == release_id).first()
    if not release:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên bản release.")

    active_using = (
        db.query(UpdateJob)
        .filter(UpdateJob.release_id == release_id, UpdateJob.status.in_(ACTIVE_JOB_STATUSES))
        .first()
    )
    if active_using:
        raise HTTPException(status_code=409, detail="Không thể xóa release đang có tiến trình cập nhật chạy.")

    try:
        Path(release.file_path).unlink(missing_ok=True)
    except OSError:
        pass

    ver = release.version
    db.delete(release)
    db.add(AccessLog(action="OTA_DELETE", details=f"Admin {admin.full_name} đã xóa gói OTA v{ver}"))
    db.commit()
    return {"success": True, "message": f"Đã xóa release v{ver}."}


@router.post("/update", status_code=status.HTTP_201_CREATED)
def trigger_update(
    payload: TriggerUpdateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Creates a PENDING OTA UPDATE job for the Raspberry Pi OTA Agent."""
    active = (
        db.query(UpdateJob)
        .filter(UpdateJob.status.in_(ACTIVE_JOB_STATUSES))
        .first()
    )
    if active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Đang có tiến trình cập nhật #{active.id} ({active.status}) chạy. Vui lòng chờ hoàn tất.",
        )

    release = db.query(SoftwareRelease).filter(SoftwareRelease.id == payload.release_id).first()
    if not release:
        raise HTTPException(status_code=404, detail="Không tìm thấy bản release yêu cầu.")

    if not Path(release.file_path).is_file():
        raise HTTPException(status_code=404, detail="File ZIP của bản release này không còn trên đĩa.")

    current_ver = get_current_app_version()
    job = UpdateJob(
        release_id=release.id,
        action="UPDATE",
        target_version=release.version,
        previous_version=current_ver,
        status="PENDING",
        progress=0,
        message=f"Đã tạo lệnh cập nhật v{current_ver} -> v{release.version}. Đang chờ OTA Agent trên Pi...",
    )
    _append_job_log(job, "PENDING", f"Admin {admin.full_name} yêu cầu cập nhật lên v{release.version}.")
    db.add(job)
    db.add(
        AccessLog(
            action="OTA_UPDATE_START",
            details=f"Admin {admin.full_name} tạo lệnh cập nhật OTA v{current_ver} -> v{release.version}",
        )
    )
    db.commit()
    db.refresh(job)
    return _serialize_job(job)


@router.post("/rollback", status_code=status.HTTP_201_CREATED)
def trigger_rollback(
    payload: TriggerRollbackRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Creates a PENDING ROLLBACK job for the Raspberry Pi OTA Agent."""
    active = (
        db.query(UpdateJob)
        .filter(UpdateJob.status.in_(ACTIVE_JOB_STATUSES))
        .first()
    )
    if active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Đang có tiến trình #{active.id} ({active.status}) chạy.",
        )

    current_ver = get_current_app_version()
    target_ver = (payload.target_version or "").strip().lstrip("vV")
    if not target_ver:
        last_success = (
            db.query(UpdateJob)
            .filter(UpdateJob.status == "SUCCESS", UpdateJob.previous_version.isnot(None))
            .order_by(UpdateJob.id.desc())
            .first()
        )
        target_ver = last_success.previous_version if last_success else ""

    if not target_ver:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Không xác định được phiên bản trước để rollback. Hãy chọn phiên bản cụ thể.",
        )

    job = UpdateJob(
        release_id=None,
        action="ROLLBACK",
        target_version=target_ver,
        previous_version=current_ver,
        status="PENDING",
        progress=0,
        message=f"Đã tạo lệnh Rollback v{current_ver} -> v{target_ver}. Đang chờ OTA Agent...",
    )
    _append_job_log(job, "PENDING", f"Admin {admin.full_name} yêu cầu rollback về v{target_ver}.")
    db.add(job)
    db.add(
        AccessLog(
            action="OTA_ROLLBACK_START",
            details=f"Admin {admin.full_name} yêu cầu rollback OTA về v{target_ver}",
        )
    )
    db.commit()
    db.refresh(job)
    return _serialize_job(job)


@router.get("/jobs")
def list_jobs(
    limit: int = 20,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    jobs = db.query(UpdateJob).order_by(UpdateJob.id.desc()).limit(max(1, min(limit, 100))).all()
    return [_serialize_job(j) for j in jobs]


@router.get("/jobs/{job_id}")
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    job = db.query(UpdateJob).filter(UpdateJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy update job.")
    return _serialize_job(job)


# ==========================================
# Raspberry Pi OTA Agent Endpoints
# ==========================================

@router.get("/agent/pending-job")
def agent_get_pending_job(
    db: Session = Depends(get_db),
    _authorized: bool = Depends(require_ota_agent),
):
    """Polled by the independent OTA Agent on Raspberry Pi to fetch pending UPDATE/ROLLBACK jobs."""
    job = (
        db.query(UpdateJob)
        .filter(UpdateJob.status == "PENDING")
        .order_by(UpdateJob.id.asc())
        .first()
    )
    if not job:
        return {"has_job": False, "job": None}

    release = db.query(SoftwareRelease).filter(SoftwareRelease.id == job.release_id).first() if job.release_id else None
    payload = {
        "job_id": job.id,
        "action": job.action,
        "target_version": job.target_version,
        "previous_version": job.previous_version,
        "release_id": job.release_id,
        "download_path": f"/api/v1/ota/agent/releases/{release.id}/download" if release else None,
        "sha256": release.sha256 if release else None,
        "signature": release.signature if release else None,
    }
    return {"has_job": True, "job": payload}


@router.get("/agent/releases/{release_id}/download")
def agent_download_release(
    release_id: int,
    db: Session = Depends(get_db),
    _authorized: bool = Depends(require_ota_agent),
):
    release = db.query(SoftwareRelease).filter(SoftwareRelease.id == release_id).first()
    if not release or not Path(release.file_path).is_file():
        raise HTTPException(status_code=404, detail="Không tìm thấy file gói OTA.")
    return FileResponse(
        path=release.file_path,
        media_type="application/zip",
        filename=release.filename,
    )


@router.post("/agent/jobs/{job_id}/status")
def agent_report_job_status(
    job_id: int,
    payload: AgentJobStatusUpdate,
    db: Session = Depends(get_db),
    _authorized: bool = Depends(require_ota_agent),
):
    job = db.query(UpdateJob).filter(UpdateJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy job.")

    now = datetime.now(timezone.utc)
    if job.started_at is None and payload.status != "PENDING":
        job.started_at = now

    job.status = payload.status
    job.progress = payload.progress
    if payload.message:
        job.message = payload.message
    _append_job_log(job, payload.status, payload.message or payload.status)

    if payload.status in TERMINAL_JOB_STATUSES:
        job.completed_at = now
        db.add(
            AccessLog(
                action=f"OTA_{payload.status}",
                details=f"OTA Job #{job.id} ({job.action} -> v{job.target_version}): {payload.status} - {payload.message}",
            )
        )

    db.commit()
    db.refresh(job)
    return _serialize_job(job)
