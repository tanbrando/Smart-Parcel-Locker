"""Capture a guided five-angle pickup and submit it to the server."""
import base64
from contextlib import ExitStack
import os
from pathlib import Path

import requests

from contracts.schemas import OtpVerificationResponse
from edge.config import CAMERA_INDEX, USE_CSI_CAMERA
from edge.cv.face_verify import FaceCamera, PiCapture, POSE_PROMPTS, cv2


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


def verify_pickup(api, user_id, indicators):
    device_key = os.environ.get("FACE_DEVICE_KEY", "").strip()
    if not device_key:
        raise RuntimeError("FACE_DEVICE_KEY is not configured. Run ./setup.sh to generate keys.")
    yunet_path = _resolve_model_path("FACE_YUNET", DEFAULT_YUNET_PATH)
    sface_path = _resolve_model_path("FACE_SFACE", DEFAULT_SFACE_PATH)
    if not yunet_path.is_file() or not sface_path.is_file():
        raise RuntimeError("Face ONNX models missing. Run ./setup.sh to download YuNet & SFace.")
    model = FaceCamera(yunet_path, sface_path)
    photos = {}
    neutral_pitch = None
    with ExitStack() as stack:
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
        for index, pose in enumerate(POSE_PROMPTS, 1):
            prompts = {"front": "Look straight", "left": "Turn left", "right": "Turn right",
                       "up": "Raise chin", "down": "Lower chin"}
            indicators.display_message(f"Face ID {index}/5", prompts[pose])
            accepted = []
            _, _, pitch = model.capture(
                camera, pose, neutral_pitch=neutral_pitch, frame_count=1,
                on_capture=accepted.append,
            )
            if pose == "front":
                neutral_pitch = pitch
            ok, image = cv2.imencode(".jpg", accepted[0], [cv2.IMWRITE_JPEG_QUALITY, 88])
            if not ok:
                raise ValueError("Could not encode camera image")
            photos[pose] = "data:image/jpeg;base64," + base64.b64encode(image).decode("ascii")
    response = requests.post(
        f"{api.base_url}/api/v1/pi/verify-face",
        json={"user_id": user_id, "angles": photos},
        headers={"X-Face-Device-Key": device_key}, timeout=max(api.timeout, 30),
    )
    response.raise_for_status()
    return OtpVerificationResponse.model_validate(response.json())
