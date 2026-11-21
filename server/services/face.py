"""Convert the five ordered camera images into SFace enrollment or probe vectors."""
import base64
import binascii
import os
from pathlib import Path


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


def extract_templates(angles):
    from edge.cv.face_verify import FaceCamera, POSE_PROMPTS, cv2, np

    if set(angles) != set(POSE_PROMPTS):
        raise ValueError("Provide front, left, right, up and down images.")
    try:
        yunet_path = _resolve_model_path("FACE_YUNET", DEFAULT_YUNET_PATH)
        sface_path = _resolve_model_path("FACE_SFACE", DEFAULT_SFACE_PATH)
        if not yunet_path.is_file() or not sface_path.is_file():
            raise FileNotFoundError(f"Missing ONNX models: {yunet_path}, {sface_path}")
        camera = FaceCamera(yunet_path, sface_path)
    except (KeyError, OSError, cv2.error) as exc:
        raise RuntimeError("Face models are unavailable. Run ./setup.sh to download YuNet & SFace ONNX models.") from exc
    neutral_pitch = None
    templates = {}
    for pose in POSE_PROMPTS:
        image = angles[pose]
        if len(image) > 1_400_000 or not image.startswith("data:image/jpeg;base64,"):
            raise ValueError(f"{pose}: expected JPEG camera image.")
        try:
            encoded = base64.b64decode(image.split(",", 1)[1], validate=True)
            frame = cv2.imdecode(np.frombuffer(encoded, np.uint8), cv2.IMREAD_COLOR)
        except (binascii.Error, cv2.error) as exc:
            raise ValueError(f"{pose}: invalid camera image.") from exc
        if frame is None:
            raise ValueError(f"{pose}: invalid camera image.")
        sample, reason = camera._inspect(frame, pose, neutral_pitch)
        if sample is None:
            raise ValueError(f"{pose}: {reason}")
        _, vector, pitch = sample
        if pose == "front":
            neutral_pitch = pitch
        templates[pose] = vector
    return camera.model_id, templates
