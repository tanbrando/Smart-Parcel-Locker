"""Convert the five ordered camera images into SFace enrollment or probe vectors."""
import base64
import binascii
import os
from pathlib import Path


def extract_templates(angles):
    from edge.cv.face_verify import FaceCamera, POSE_PROMPTS, cv2, np

    if set(angles) != set(POSE_PROMPTS):
        raise ValueError("Provide front, left, right, up and down images.")
    try:
        camera = FaceCamera(Path(os.environ["FACE_YUNET"]), Path(os.environ["FACE_SFACE"]))
    except (KeyError, OSError, cv2.error) as exc:
        raise RuntimeError("Face models are unavailable.") from exc
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
