"""
Authentication & Multi-Angle Face Recognition Enrollment Router.
Handles User/Admin login, session inspection, and 5-angle facial authentication setup.
"""
import json
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from contracts.schemas import (
    LoginRequest,
    LoginResponse,
    UserResponse,
    UserRole,
    FaceToggleRequest,
    FaceEnrollMultiAngleRequest,
    FaceCheckAngleRequest,
    FaceCheckAngleResponse,
    FaceEnrollResponse,
)
from server.core.security import (
    verify_password,
    create_session_token,
    parse_session_token,
)
from server.db.session import get_db
from server.db.models import User, AccessLog
from server.services.face import extract_templates, inspect_single_angle

router = APIRouter(prefix="/auth", tags=["Authentication & Face ID"])

REQUIRED_FACE_ANGLES = ("front", "left", "right", "up", "down")


def require_face_account(authorization, user_id):
    session = (
        parse_session_token(authorization[7:])
        if authorization and authorization.startswith("Bearer ") else None
    )
    if not session or session[0] != user_id:
        raise HTTPException(status_code=403, detail="Vui lòng đăng nhập bằng tài khoản cần thay đổi.")


def _serialize_user(user: User) -> UserResponse:
    role_val = user.role if user.role in ("USER", "ADMIN") else "USER"
    return UserResponse(
        id=user.id,
        full_name=user.full_name,
        phone=user.phone,
        phone_last4=user.phone_last4,
        role=UserRole(role_val),
        telegram_chat_id=user.telegram_chat_id,
        face_auth_enabled=bool(user.face_auth_enabled),
        face_registered=bool(user.face_registered),
        face_angles_enrolled=user.face_angles_enrolled,
        created_at=user.created_at,
    )


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """Authenticates a User or Admin by phone number and password."""
    clean_phone = payload.phone.strip()
    user = db.query(User).filter(User.phone == clean_phone).first()

    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Số điện thoại hoặc mật khẩu không chính xác.",
        )

    role_str = user.role or "USER"
    token = create_session_token(user.id, role_str)
    redirect_url = "/" if role_str == UserRole.ADMIN.value else "/portal"

    return LoginResponse(
        success=True,
        token=token,
        user=_serialize_user(user),
        redirect_url=redirect_url,
    )


@router.get("/me", response_model=UserResponse)
def get_current_user(
    authorization: Optional[str] = Header(None),
    user_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Returns current authenticated user info from Bearer token or user_id query."""
    resolved_id = user_id
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        parsed = parse_session_token(token)
        if not parsed:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Phiên đăng nhập không hợp lệ hoặc đã hết hạn.",
            )
        resolved_id = parsed[0]

    if not resolved_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Vui lòng đăng nhập để tiếp tục.",
        )

    user = db.query(User).filter(User.id == resolved_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy tài khoản.")
    return _serialize_user(user)


@router.post("/face/toggle", response_model=FaceEnrollResponse)
def toggle_face_auth(payload: FaceToggleRequest, db: Session = Depends(get_db),
                     authorization: Optional[str] = Header(None)):
    """Enables or disables facial authentication for a specific user."""
    require_face_account(authorization, payload.user_id)
    user = db.query(User).filter(User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy người dùng.")

    if payload.enabled and not bool(user.face_registered):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bạn cần đăng ký khuôn mặt đa góc độ (5 góc) trước khi kích hoạt.",
        )

    user.face_auth_enabled = 1 if payload.enabled else 0
    db.add(
        AccessLog(
            action="FACE_AUTH_TOGGLE",
            details=f"User #{user.id} ({user.full_name}) {'enabled' if payload.enabled else 'disabled'} Face ID",
        )
    )
    db.commit()
    db.refresh(user)

    return FaceEnrollResponse(
        success=True,
        user_id=user.id,
        face_auth_enabled=bool(user.face_auth_enabled),
        face_registered=bool(user.face_registered),
        enrolled_angles=user.face_angles_enrolled,
        message="Đã bật xác thực khuôn mặt." if payload.enabled else "Đã tắt xác thực khuôn mặt.",
    )


@router.post("/face/check-angle", response_model=FaceCheckAngleResponse)
def check_face_angle(payload: FaceCheckAngleRequest):
    """Validates a single camera frame with YuNet during guided 5-angle Web enrollment."""
    try:
        result = inspect_single_angle(
            pose=payload.pose,
            image=payload.image,
            neutral_pitch=payload.neutral_pitch,
        )
        return FaceCheckAngleResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/face/enroll", response_model=FaceEnrollResponse)
def enroll_face_multi_angle(payload: FaceEnrollMultiAngleRequest, db: Session = Depends(get_db),
                            authorization: Optional[str] = Header(None)):
    """Stores 5-angle facial registration data (front, left, right, up, down) and activates Face ID."""
    require_face_account(authorization, payload.user_id)
    user = db.query(User).filter(User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy người dùng.")

    provided_angles = {
        k: v for k, v in payload.angles.items() if k in REQUIRED_FACE_ANGLES and isinstance(v, str) and len(v.strip()) > 0
    }
    missing = [angle for angle in REQUIRED_FACE_ANGLES if angle not in provided_angles]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Thiếu dữ liệu góc chụp khuôn mặt: {', '.join(missing)}. Cần đủ 5 góc.",
        )

    try:
        model_id, templates = extract_templates(provided_angles)
        if any(float(templates["front"] @ vector) < 0.45 for vector in templates.values()):
            raise ValueError("Các ảnh đăng ký phải thuộc cùng một người.")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    stored_payload = {
        angle: {"model_id": model_id, "embedding": vector.tolist()}
        for angle, vector in templates.items()
    }

    user.face_data_json = json.dumps(stored_payload, ensure_ascii=False)
    user.face_registered = 1
    user.face_auth_enabled = 1

    db.add(
        AccessLog(
            action="FACE_ENROLLED",
            details=f"User #{user.id} ({user.full_name}) enrolled 5-angle Face ID ({', '.join(REQUIRED_FACE_ANGLES)})",
        )
    )
    db.commit()
    db.refresh(user)

    return FaceEnrollResponse(
        success=True,
        user_id=user.id,
        face_auth_enabled=True,
        face_registered=True,
        enrolled_angles=user.face_angles_enrolled,
        message="Đăng ký khuôn mặt đa góc độ thành công và đã kích hoạt Face ID!",
    )


@router.get("/face/status/{user_id}", response_model=FaceEnrollResponse)
def get_face_status(user_id: int, db: Session = Depends(get_db)):
    """Returns Face ID registration and activation status for a user."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy người dùng.")

    return FaceEnrollResponse(
        success=True,
        user_id=user.id,
        face_auth_enabled=bool(user.face_auth_enabled),
        face_registered=bool(user.face_registered),
        enrolled_angles=user.face_angles_enrolled,
        message="Đã kích hoạt Face ID" if user.face_auth_enabled else "Face ID đang tắt",
    )
