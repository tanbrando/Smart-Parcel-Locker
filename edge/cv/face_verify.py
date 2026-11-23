"""Local 1:1 face verification with guided enrollment and bounded adaptation."""
import argparse
import contextlib
import hashlib
import json
from pathlib import Path
import sqlite3
import time

import cv2
import numpy as np


POSE_PROMPTS = {
    "front": "Look straight at the camera",
    "left": "Turn slightly to your left",
    "right": "Turn slightly to your right",
    "up": "Raise your chin slightly",
    "down": "Lower your chin slightly",
}
VERIFY_SCORE = 0.50
ADAPT_SCORE = 0.70
ANCHOR_SCORE = 0.45
PREVIEW_TITLE = "Smart Parcel Locker - Face Verification"
PITCH_UP_MIN = 0.04
PITCH_DOWN_MIN = 0.03
PITCH_FRONT_MARGIN = 0.008
PITCH_MAX = 0.30


def show_preview(frame, prompt, progress, status):
    image = cv2.flip(frame, 1)
    height, width = image.shape[:2]
    scale = max(0.35, min(0.85, width / 780))
    cv2.rectangle(image, (0, 0), (width, 82), (20, 20, 20), -1)
    cv2.ellipse(image, (width // 2, height // 2), (width // 5, height // 3),
                0, 0, 360, (100, 220, 140), 2)
    for y, line in (
        (22, f"{progress}{prompt}"),
        (47, status),
        (72, "Esc or Q to cancel"),
    ):
        cv2.putText(image, line, (12, y), cv2.FONT_HERSHEY_SIMPLEX,
                    scale, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.imshow(PREVIEW_TITLE, image)
    key = cv2.waitKey(1) & 0xFF
    if key in (27, ord("q"), ord("Q")) or cv2.getWindowProperty(
        PREVIEW_TITLE, cv2.WND_PROP_VISIBLE
    ) < 1:
        raise ValueError("Capture cancelled")


def unit(vector):
    vector = np.asarray(vector, dtype=np.float32).reshape(128)
    norm = np.linalg.norm(vector)
    if not np.isfinite(norm) or norm <= 0:
        raise ValueError("Invalid SFace embedding")
    return vector / norm


def pose_geometry(landmarks):
    eye_a, eye_b, nose, mouth_a, mouth_b = landmarks
    left, right = sorted((eye_a, eye_b), key=lambda point: point[0])
    axis = right - left
    distance_squared = float(axis @ axis)
    if distance_squared < 400:
        return None
    yaw = float((nose - (left + right) / 2) @ axis) / distance_squared
    vertical = np.array([-axis[1], axis[0]])
    eyes = (left + right) / 2
    mouth_depth = float(((mouth_a + mouth_b) / 2 - eyes) @ vertical)
    if mouth_depth < 0.30 * distance_squared:
        return None
    pitch = float((nose - eyes) @ vertical) / mouth_depth
    if not 0 < pitch < 1:
        return None
    return yaw, pitch


def classify_pose(yaw, pitch, neutral_pitch):
    delta = 0 if neutral_pitch is None else pitch - neutral_pitch
    if abs(yaw) <= 0.22:
        if -PITCH_MAX <= delta <= -PITCH_UP_MIN:
            return "up"
        if PITCH_DOWN_MIN <= delta <= PITCH_MAX:
            return "down"
    if abs(delta) > 0.12:
        return None
    if abs(yaw) <= 0.14 and (
        -PITCH_UP_MIN + PITCH_FRONT_MARGIN <= delta <= PITCH_DOWN_MIN - PITCH_FRONT_MARGIN
    ):
        return "front"
    if 0.18 <= yaw <= 0.65:
        return "left"
    if -0.65 <= yaw <= -0.18:
        return "right"
    return None


class FaceCamera:
    def __init__(self, detector_path, recognizer_path):
        self.detector = cv2.FaceDetectorYN.create(str(detector_path), "", (320, 320), 0.80)
        self.recognizer = cv2.FaceRecognizerSF.create(str(recognizer_path), "")
        with recognizer_path.open("rb") as model:
            self.model_id = hashlib.sha256(model.read()).hexdigest()

    def sample(self, frame):
        result, _ = self._inspect(frame)
        return result[:2] if result is not None else None

    def _inspect(self, frame, required_pose=None, neutral_pitch=None):
        height, width = frame.shape[:2]
        self.detector.setInputSize((width, height))
        _, faces = self.detector.detect(frame)
        if faces is None or len(faces) != 1:
            return None, "Keep exactly one face in view"
        face = faces[0]
        x, y, box_width, box_height = face[:4]
        if min(box_width, box_height) < 100:
            return None, "Move a little closer"
        if x < 0 or y < 0 or x + box_width > width or y + box_height > height:
            return None, "Keep your whole face in the frame"
        geometry = pose_geometry(face[4:14].reshape(5, 2))
        if geometry is None:
            return None, "Keep eyes, nose and mouth visible"
        yaw, pitch = geometry
        pose = classify_pose(yaw, pitch, neutral_pitch)
        if required_pose in ("up", "down") and pose != required_pose and neutral_pitch is not None:
            if abs(yaw) > 0.22:
                return None, "Face the camera without turning sideways"
            movement = pitch - neutral_pitch if required_pose == "down" else neutral_pitch - pitch
            if movement > PITCH_MAX:
                return None, "Bring your chin a little closer to neutral"
            direction = "Raise" if required_pose == "up" else "Lower"
            return None, f"{direction} your chin a little more"
        if required_pose is None:
            if abs(yaw) > 0.45:
                return None, "Face the camera more directly"
            pose = pose or "front"
        elif pose is None or pose != required_pose:
            return None, f"Detected pose: {pose or 'between poses'}"
        aligned = self.recognizer.alignCrop(frame, face)
        gray = cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY)
        if not 50 <= gray.mean() <= 205:
            return None, "Adjust the lighting on your face"
        if cv2.Laplacian(gray, cv2.CV_64F).var() < 45:
            return None, "Image blurred: hold still"
        return (pose, unit(self.recognizer.feature(aligned)), pitch), ""

    def capture(self, camera, required_pose=None, anchor=None, preview=False,
                neutral_pitch=None, frame_count=3, on_capture=None):
        prompt = POSE_PROMPTS[required_pose] if required_pose else "Show one face in good light"
        print(prompt + " and hold still.", flush=True)
        deadline = time.monotonic() + 20
        previous_pose = None
        samples = []
        progress = ""
        if required_pose is not None:
            step = tuple(POSE_PROMPTS).index(required_pose) + 1
            progress = f"{step}/{len(POSE_PROMPTS)}  "
        status = "Waiting for a camera frame"
        while time.monotonic() < deadline:
            ok, frame = camera.read()
            if not ok:
                status = "Waiting for a camera frame"
                result = None
            else:
                result, status = self._inspect(frame, required_pose, neutral_pitch)
            if result is not None and anchor is not None and float(anchor @ result[1]) < ANCHOR_SCORE:
                result = None
                status = "Face match is weak: turn a little less"
            if result is None:
                samples.clear()
                previous_pose = None
            else:
                pose, vector, pitch = result
                consistent = not samples or float(samples[0] @ vector) >= ADAPT_SCORE
                if previous_pose != pose or not consistent:
                    samples.clear()
                previous_pose = pose
                samples.append(vector)
                status = f"Hold still: {pose} accepted ({len(samples)}/{frame_count})"
            if preview and ok:
                show_preview(frame, prompt, progress, status)
            if len(samples) == frame_count:
                if on_capture is not None:
                    on_capture(frame)
                print("Captured.", flush=True)
                return pose, unit(np.mean(samples, axis=0)), pitch
            time.sleep(0.12)
        raise TimeoutError(f"No stable face captured within 20 seconds. Last status: {status}")


class FaceProfiles:
    def __init__(self, db, model_id):
        self.db = db
        self.model_id = model_id
        db.execute("""CREATE TABLE IF NOT EXISTS face_profiles (
            user_id TEXT PRIMARY KEY, model_id TEXT NOT NULL,
            anchors TEXT NOT NULL, adaptive TEXT NOT NULL
        )""")

    def enroll(self, user_id, anchors):
        if set(anchors) != set(POSE_PROMPTS):
            raise ValueError("Enrollment requires all five poses")
        anchors = {pose: unit(vector) for pose, vector in anchors.items()}
        if any(float(anchors["front"] @ vector) < ANCHOR_SCORE for vector in anchors.values()):
            raise ValueError("Enrollment samples are inconsistent")
        payload = json.dumps({pose: vector.tolist() for pose, vector in anchors.items()})
        with self.db:
            saved = self.db.execute(
                """INSERT INTO face_profiles (user_id, model_id, anchors, adaptive)
                   VALUES (?, ?, ?, '{}')
                   ON CONFLICT(user_id) DO UPDATE SET
                       anchors = excluded.anchors, adaptive = excluded.adaptive
                   WHERE face_profiles.model_id = excluded.model_id
                     AND (json_type(face_profiles.anchors, '$.up') IS NULL
                          OR json_type(face_profiles.anchors, '$.down') IS NULL)""",
                (user_id, self.model_id, payload),
            )
            if saved.rowcount != 1:
                raise ValueError("This ID already has a face profile")

    def require_profile(self, user_id):
        row = self.db.execute(
            "SELECT model_id, anchors, adaptive FROM face_profiles WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row is None or row[0] != self.model_id:
            raise ValueError(f"No profile for {user_id!r} with the current model. Run enroll first.")
        return row

    def verify(self, user_id, pose, vector, adapt=False):
        if pose not in POSE_PROMPTS:
            raise ValueError("Unknown pose")
        vector = unit(vector)
        # Serialize the read/modify/write so competing updates cannot overwrite each other.
        with self.db:
            if adapt:
                self.db.execute("BEGIN IMMEDIATE")
            row = self.require_profile(user_id)
            anchors, adaptive = map(json.loads, row[1:])
            if pose not in anchors:
                return False
            anchor = unit(anchors[pose])
            current = unit(adaptive[pose]) if pose in adaptive else anchor
            anchor_score = float(anchor @ vector)
            match = anchor_score >= ANCHOR_SCORE and max(anchor_score, float(current @ vector)) >= VERIFY_SCORE
            if adapt and match and anchor_score >= ADAPT_SCORE:
                candidate = unit(0.90 * current + 0.10 * vector)
                if float(anchor @ candidate) >= 0.90:
                    adaptive[pose] = candidate.tolist()
                    self.db.execute(
                        "UPDATE face_profiles SET adaptive = ? WHERE user_id = ?",
                        (json.dumps(adaptive), user_id),
                    )
        return match


def read_photos(paths):
    if len(paths) != 5 or len({Path(path).resolve() for path in paths}) != 5:
        raise ValueError("Provide five distinct photo paths")
    frames = []
    for path in paths:
        frame = cv2.imread(str(path))
        if frame is None:
            raise ValueError(f"Cannot read photo: {path}")
        frames.append(frame)
    return frames


class PiCapture:
    def __init__(self, camera):
        self.camera = camera

    def read(self):
        frame = self.camera.capture_array()
        return frame is not None, frame


def guided_session(face_camera, profiles, args, camera):
    if args.action == "adapt":
        pose, vector, _ = face_camera.capture(camera, preview=args.preview)
        return profiles.verify(args.user_id, pose, vector, adapt=True)
    anchors = {}
    neutral_pitch = None
    for expected in POSE_PROMPTS:
        pose, vector, pitch = face_camera.capture(
            camera, expected, anchor=anchors.get("front"), preview=args.preview,
            neutral_pitch=neutral_pitch, frame_count=3 if args.action == "enroll" else 1,
        )
        if pose == "front":
            neutral_pitch = pitch
        if args.action == "verify":
            if not profiles.verify(args.user_id, pose, vector):
                print(f"{pose}: No match", flush=True)
                return False
            print(f"{pose}: Match", flush=True)
        else:
            anchors[pose] = vector
    if args.action == "enroll":
        profiles.enroll(args.user_id, anchors)
        print("Saved all five poses.", flush=True)
    return True


def verify_five(face_camera, profiles, user_id, frames):
    if len(frames) != len(POSE_PROMPTS):
        raise ValueError("Verification requires exactly five images")
    neutral_pitch = None
    for index, (expected, frame) in enumerate(zip(POSE_PROMPTS, frames), 1):
        sample, reason = face_camera._inspect(frame, expected, neutral_pitch)
        if sample is None:
            print(f"Image {index}/5 ({expected}): {reason}")
            return False
        pose, vector, pitch = sample
        if not profiles.verify(user_id, pose, vector):
            print(f"Image {index}/5 ({expected}): No match")
            return False
        if pose == "front":
            neutral_pitch = pitch
        print(f"Image {index}/5 ({expected}): Match")
    return True


def main():
    parser = argparse.ArgumentParser(description="Local face verification prototype")
    parser.add_argument("action", choices=("enroll", "verify", "adapt"))
    parser.add_argument("user_id", help="Claimed identity supplied by the local operator")
    parser.add_argument("--yunet", type=Path, required=True)
    parser.add_argument("--sface", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True, help="Private SQLite path outside the repo")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--preview", action="store_true", help="Show a live webcam window")
    parser.add_argument("--photos", nargs=5, type=Path, metavar="IMAGE",
                        help="Verify five images captured by the Pi")
    parser.add_argument("--picamera2", action="store_true", help="Use a Raspberry Pi CSI camera")
    args = parser.parse_args()
    if args.photos and (args.action != "verify" or args.preview):
        parser.error("--photos requires verify without --preview")
    if args.picamera2 and args.photos:
        parser.error("--picamera2 requires live capture")
    try:
        if args.preview and not getattr(cv2, "currentUIFramework", lambda: "unknown")():
            raise ValueError("--preview requires the desktop opencv-python package")
        face_camera = FaceCamera(args.yunet, args.sface)
        with contextlib.closing(sqlite3.connect(args.db)) as db:
            profiles = FaceProfiles(db, face_camera.model_id)
            if args.action != "enroll":
                row = profiles.require_profile(args.user_id)
                if args.action == "verify" and not set(POSE_PROMPTS).issubset(json.loads(row[1])):
                    raise ValueError("Profile is missing poses. Run enroll with the same ID to upgrade it.")
            if args.photos:
                match = verify_five(face_camera, profiles, args.user_id, read_photos(args.photos))
            else:
                try:
                    if args.picamera2:
                        from picamera2 import Picamera2
                        with Picamera2(args.camera) as pi:
                            config = pi.create_preview_configuration(
                                main={"size": (640, 480), "format": "RGB888"}
                            )
                            pi.configure(config)
                            pi.start()
                            time.sleep(1)
                            match = guided_session(face_camera, profiles, args, PiCapture(pi))
                    else:
                        camera = cv2.VideoCapture(args.camera)
                        try:
                            if not camera.isOpened():
                                raise ValueError("Cannot open camera")
                            match = guided_session(face_camera, profiles, args, camera)
                        finally:
                            camera.release()
                finally:
                    if args.preview:
                        cv2.destroyAllWindows()
            if args.action != "enroll":
                print("Match" if match else "No match")
            return 0 if match else 1
    except (ImportError, RuntimeError, OSError, ValueError, TimeoutError, sqlite3.Error, cv2.error) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    raise SystemExit(main())

