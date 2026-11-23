"""Capture a single-look face image at the locker and submit it for 1:N verification."""
import base64
from contextlib import ExitStack
import os
from pathlib import Path
from typing import Optional

import requests

from contracts.schemas import OtpVerificationResponse
from edge.config import CAMERA_INDEX, CAMERA_PREVIEW, USE_CSI_CAMERA
from edge.cv.face_verify import FaceCamera, PiCapture, cv2


def _preview_enabled() -> bool:
    want = os.getenv("CAMERA_PREVIEW", str(CAMERA_PREVIEW)).lower() in ("true", "1", "yes")
    if not want:
        return False
    if os.name != "nt" and not os.environ.get("DISPLAY"):
        return False
    try:
        ui_fw = getattr(cv2, "currentUIFramework", None)
        if callable(ui_fw) and not ui_fw():
            return False
    except Exception:
        return False
    return True


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_YUNET_PATH = REPO_ROOT / "edge" / "models" / "face" / "face_detection_yunet_2023mar.onnx"
DEFAULT_SFACE_PATH = REPO_ROOT / "edge" / "models" / "face" / "face_recognition_sface_2021dec.onnx"


def _resolve_model_path(env_var: str, default_path: Path) -> Path:
    raw = os.environ.get(env_var, "").strip()
    if raw:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = REPO_ROOT / candidate
        return candidate
    return default_path


def verify_pickup(api, user_id: Optional[int] = None, indicators=None):
    """Captures one clear look at the locker camera and requests 1:N (or optional 1:1) unlock."""
    device_key = os.environ.get("FACE_DEVICE_KEY", "").strip()
    if not device_key:
        raise RuntimeError("FACE_DEVICE_KEY is not configured. Run ./setup.sh to generate keys.")
    yunet_path = _resolve_model_path("FACE_YUNET", DEFAULT_YUNET_PATH)
    sface_path = _resolve_model_path("FACE_SFACE", DEFAULT_SFACE_PATH)
    if not yunet_path.is_file() or not sface_path.is_file():
        raise RuntimeError("Face ONNX models missing. Run ./setup.sh to download YuNet & SFace.")
    model = FaceCamera(yunet_path, sface_path)
    use_preview = _preview_enabled()
    accepted = []
    with ExitStack() as stack:
        if use_preview:
            stack.callback(cv2.destroyAllWindows)
        if USE_CSI_CAMERA:
            from picamera2 import Picamera2

            pi = stack.enter_context(Picamera2(CAMERA_INDEX))
            pi.configure(pi.create_preview_configuration(main={"size": (640, 480), "format": "RGB888"}))
            pi.start()
            camera = PiCapture(pi)
        else:
            camera = cv2.VideoCapture(CAMERA_INDEX)
            stack.callback(camera.release)
            if not camera.isOpened():
                raise ValueError("Cannot open camera")
        if indicators is not None:
            indicators.display_message("Face ID Pickup", "Look at camera")
        model.capture(
            camera,
            required_pose=None,
            preview=use_preview,
            frame_count=2,
            on_capture=accepted.append,
        )
    ok, image = cv2.imencode(".jpg", accepted[0], [cv2.IMWRITE_JPEG_QUALITY, 88])
    if not ok:
        raise ValueError("Could not encode camera image")
    payload = {
        "image": "data:image/jpeg;base64," + base64.b64encode(image).decode("ascii"),
    }
    if user_id is not None:
        payload["user_id"] = int(user_id)
    response = requests.post(
        f"{api.base_url}/api/v1/pi/verify-face",
        json=payload,
        headers={"X-Face-Device-Key": device_key},
        timeout=max(api.timeout, 30),
    )
    response.raise_for_status()
    return OtpVerificationResponse.model_validate(response.json())
