"""Convert the five ordered camera images into SFace enrollment or probe vectors,
and provide real-time single-angle YuNet pose validation for the Web enrollment HUD."""
import base64
import binascii
import os
import threading
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_YUNET_PATH = REPO_ROOT / "edge" / "models" / "face" / "face_detection_yunet_2023mar.onnx"
DEFAULT_SFACE_PATH = REPO_ROOT / "edge" / "models" / "face" / "face_recognition_sface_2021dec.onnx"

POSE_LABELS_VI = {
    "front": "Nhìn thẳng",
    "left": "Quay trái",
    "right": "Quay phải",
    "up": "Ngẩng lên",
    "down": "Cúi xuống",
}

_camera_lock = threading.Lock()
_cached_camera_key = None
_cached_camera = None


def _resolve_model_path(env_var: str, default_path: Path) -> Path:
    raw = os.environ.get(env_var, "").strip()
    if raw:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = REPO_ROOT / candidate
        return candidate
    return default_path


def _get_face_camera():
    """Returns a cached FaceCamera instance (avoids reloading the 38MB SFace ONNX on every frame)."""
    global _cached_camera_key, _cached_camera
    from edge.cv.face_verify import FaceCamera, cv2

    yunet_path = _resolve_model_path("FACE_YUNET", DEFAULT_YUNET_PATH)
    sface_path = _resolve_model_path("FACE_SFACE", DEFAULT_SFACE_PATH)
    key = (str(yunet_path), str(sface_path))

    with _camera_lock:
        if _cached_camera is not None and _cached_camera_key == key:
            return _cached_camera
        try:
            if not yunet_path.is_file() or not sface_path.is_file():
                raise FileNotFoundError(f"Missing ONNX models: {yunet_path}, {sface_path}")
            cam = FaceCamera(yunet_path, sface_path)
        except (KeyError, OSError, cv2.error) as exc:
            raise RuntimeError(
                "Chưa có model Face ID (YuNet/SFace). Hãy chạy ./setup.sh trên Pi để tự động tải model."
            ) from exc
        _cached_camera = cam
        _cached_camera_key = key
        return cam


def _decode_jpeg_data_url(image: str, pose: str):
    from edge.cv.face_verify import cv2, np

    label = POSE_LABELS_VI.get(pose, pose)
    if not isinstance(image, str) or len(image) > 1_400_000 or not image.startswith("data:image/jpeg;base64,"):
        raise ValueError(f"{label}: định dạng ảnh JPEG không hợp lệ.")
    try:
        encoded = base64.b64decode(image.split(",", 1)[1], validate=True)
        frame = cv2.imdecode(np.frombuffer(encoded, np.uint8), cv2.IMREAD_COLOR)
    except (binascii.Error, cv2.error) as exc:
        raise ValueError(f"{label}: không thể giải mã ảnh camera.") from exc
    if frame is None:
        raise ValueError(f"{label}: ảnh camera bị trống.")
    return frame


def _translate_reason_vi(reason: str, required_pose: str) -> str:
    """Translates FaceCamera._inspect English messages into actionable Vietnamese guidance."""
    if not reason:
        return f"Đã khớp góc {POSE_LABELS_VI.get(required_pose, required_pose)}!"
    if "exactly one face" in reason:
        return "Đưa đúng 1 khuôn mặt vào giữa khung"
    if "Move a little closer" in reason:
        return "Đưa mặt lại gần camera hơn một chút"
    if "whole face in the frame" in reason:
        return "Giữ toàn bộ khuôn mặt nằm gọn trong khung"
    if "eyes, nose and mouth" in reason:
        return "Giữ rõ 2 mắt, mũi và miệng"
    if "without turning sideways" in reason:
        return "Giữ mặt hướng thẳng, không quay ngang"
    if "closer to neutral" in reason:
        return "Nghiêng nhẹ lại một chút (hơi quá góc)"
    if "Raise your chin" in reason:
        return "Ngẩng cằm lên cao hơn một chút"
    if "Lower your chin" in reason:
        return "Cúi cằm xuống thấp hơn một chút"
    if "Adjust the lighting" in reason:
        return "Điều chỉnh ánh sáng trên khuôn mặt (tránh quá tối/chói)"
    if "Image blurred" in reason:
        return "Ảnh hơi mờ — hãy giữ yên đầu"
    if reason.startswith("Detected pose:"):
        target_hints = {
            "front": "Hãy nhìn thẳng trực diện vào camera",
            "left": "Hãy quay mặt sang TRÁI thêm một chút",
            "right": "Hãy quay mặt sang PHẢI thêm một chút",
            "up": "Hãy ngẩng nhẹ cằm LÊN TRÊN",
            "down": "Hãy cúi nhẹ cằm XUỐNG DƯỚI",
        }
        return target_hints.get(required_pose, reason)
    return reason


def inspect_single_angle(pose: str, image: str, neutral_pitch: Optional[float] = None) -> dict:
    """Validates a single camera frame against YuNet + pose rules and returns mirrored HUD nose coordinates."""
    from edge.cv.face_verify import POSE_PROMPTS, classify_pose, pose_geometry

    if pose not in POSE_PROMPTS:
        raise ValueError("Góc chụp không hợp lệ (cần: front, left, right, up, down).")

    frame = _decode_jpeg_data_url(image, pose)
    camera = _get_face_camera()
    height, width = frame.shape[:2]

    nose_x = None
    nose_y = None
    detected_pose = None
    computed_pitch = neutral_pitch

    # Run detection + inspection inside lock (cv2.FaceDetectorYN is not thread-safe)
    with _camera_lock:
        camera.detector.setInputSize((width, height))
        _, faces = camera.detector.detect(frame)
        if faces is not None and len(faces) == 1:
            face = faces[0]
            # Landmark index 2 is nose tip (x=face[8], y=face[9]); mirror X for selfie HUD (400x300)
            nose_x = round(400.0 - (float(face[8]) / max(1, width)) * 400.0, 1)
            nose_y = round((float(face[9]) / max(1, height)) * 300.0, 1)
            geom = pose_geometry(face[4:14].reshape(5, 2))
            if geom is not None:
                detected_pose = classify_pose(geom[0], geom[1], neutral_pitch)

        sample, reason = camera._inspect(frame, pose, neutral_pitch)

    if sample is not None:
        matched_pose, _, pitch = sample
        if pose == "front":
            computed_pitch = float(pitch)
        return {
            "valid": True,
            "pose": pose,
            "detected_pose": matched_pose,
            "neutral_pitch": computed_pitch,
            "nose_x": nose_x,
            "nose_y": nose_y,
            "message": f"Đã khớp góc {POSE_LABELS_VI.get(pose, pose)}!",
        }

    return {
        "valid": False,
        "pose": pose,
        "detected_pose": detected_pose,
        "neutral_pitch": computed_pitch,
        "nose_x": nose_x,
        "nose_y": nose_y,
        "message": _translate_reason_vi(reason, pose),
    }


def extract_templates(angles):
    from edge.cv.face_verify import POSE_PROMPTS

    if set(angles) != set(POSE_PROMPTS):
        raise ValueError("Vui lòng cung cấp đủ 5 góc: Nhìn thẳng, Quay trái, Quay phải, Ngẩng lên, Cúi xuống.")
    camera = _get_face_camera()
    neutral_pitch = None
    templates = {}
    with _camera_lock:
        for pose in POSE_PROMPTS:
            frame = _decode_jpeg_data_url(angles[pose], pose)
            sample, reason = camera._inspect(frame, pose, neutral_pitch)
            if sample is None:
                label = POSE_LABELS_VI.get(pose, pose)
                raise ValueError(f"Góc {label}: {_translate_reason_vi(reason, pose)}")
            _, vector, pitch = sample
            if pose == "front":
                neutral_pitch = pitch
            templates[pose] = vector
    return camera.model_id, templates
