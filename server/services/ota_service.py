"""
OTA Software Update Core Service (Signing, Hashing, Safe ZIP Validation).
Shared by both FastAPI Backend and Raspberry Pi OTA Agent.
"""
import hashlib
import hmac
import json
import os
import re
import zipfile
from pathlib import Path
from typing import Dict, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VERSION_FILE = REPO_ROOT / "VERSION"
DEFAULT_OTA_STORAGE_DIR = REPO_ROOT / "ota_storage" / "releases"

MAX_OTA_ZIP_BYTES = int(os.getenv("MAX_OTA_ZIP_BYTES", str(100 * 1024 * 1024)))  # 100 MB
MAX_UNZIPPED_BYTES = int(os.getenv("MAX_UNZIPPED_BYTES", str(250 * 1024 * 1024)))  # 250 MB
MAX_UNZIPPED_FILES = int(os.getenv("MAX_UNZIPPED_FILES", "5000"))

SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+([\-+][0-9A-Za-z\.\-]+)?$")


def get_current_app_version() -> str:
    """Reads the currently running application version from REPO_ROOT/VERSION."""
    try:
        if VERSION_FILE.is_file():
            ver = VERSION_FILE.read_text(encoding="utf-8").strip()
            if ver:
                return ver
    except OSError:
        pass
    return "1.0.0"


def get_ota_signing_key() -> str:
    """Returns shared HMAC signing secret for OTA releases."""
    env_key = os.getenv("OTA_SIGNING_KEY", "").strip()
    if env_key:
        return env_key
    try:
        from server.core.config import settings
        return settings.SECRET_KEY
    except Exception:
        return "smart-parcel-locker-ota-default-key"


def get_ota_agent_key() -> str:
    """Returns shared authentication key for the Raspberry Pi OTA Agent."""
    env_key = os.getenv("OTA_AGENT_KEY", "").strip()
    if env_key:
        return env_key
    return get_ota_signing_key()


def compute_file_sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sign_release_hash(sha256_hex: str, version: str, secret: Optional[str] = None) -> str:
    """Computes HMAC-SHA256 signature binding version and package SHA-256."""
    key = (secret or get_ota_signing_key()).encode("utf-8")
    msg = f"{version}:{sha256_hex}".encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def verify_release_signature(
    sha256_hex: str,
    version: str,
    signature: str,
    secret: Optional[str] = None,
) -> bool:
    expected = sign_release_hash(sha256_hex, version, secret=secret)
    return hmac.compare_digest(expected, (signature or "").strip())


def validate_zip_archive(
    zip_path: Path,
    expected_version: Optional[str] = None,
) -> Tuple[bool, str, Dict]:
    """
    Validates an OTA ZIP archive before accepting or extracting:
    - Valid ZIP format & within size limits
    - Rejects absolute paths, path traversal ('..'), and symlinks (Zip Slip protection)
    - Rejects zip bombs (total uncompressed size & file count limits)
    - Validates manifest.json if present (and checks version match)
    """
    if not zip_path.is_file():
        return False, "File ZIP không tồn tại.", {}

    if zip_path.stat().st_size > MAX_OTA_ZIP_BYTES:
        return False, f"File ZIP vượt quá giới hạn {MAX_OTA_ZIP_BYTES // (1024 * 1024)} MB.", {}

    if not zipfile.is_zipfile(zip_path):
        return False, "File tải lên không phải định dạng ZIP hợp lệ.", {}

    manifest: Dict = {}
    total_uncompressed = 0

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            infos = zf.infolist()
            if len(infos) == 0:
                return False, "File ZIP rỗng.", {}
            if len(infos) > MAX_UNZIPPED_FILES:
                return False, f"File ZIP chứa quá nhiều tệp ({len(infos)} > {MAX_UNZIPPED_FILES}).", {}

            for info in infos:
                name = info.filename.replace("\\", "/")
                # Reject absolute paths or path traversal
                if name.startswith("/") or re.match(r"^[A-Za-z]:", name):
                    return False, f"Đường dẫn tuyệt đối không hợp lệ trong ZIP: {info.filename}", {}
                parts = Path(name).parts
                if ".." in parts:
                    return False, f"Phát hiện path traversal ('..') trong ZIP: {info.filename}", {}

                # Reject symlinks (UNIX mode 0o120000 in upper 16 bits of external_attr)
                unix_mode = (info.external_attr >> 16) & 0o170000
                if unix_mode == 0o120000:
                    return False, f"Không cho phép symlink bên trong gói ZIP: {info.filename}", {}

                total_uncompressed += info.file_size
                if total_uncompressed > MAX_UNZIPPED_BYTES:
                    return False, "Tổng dung lượng giải nén vượt quá giới hạn an toàn (zip bomb).", {}

            if "manifest.json" in zf.namelist():
                raw_manifest = zf.read("manifest.json").decode("utf-8")
                manifest = json.loads(raw_manifest)
                manifest_ver = str(manifest.get("version", "")).strip()
                if expected_version and manifest_ver and manifest_ver != expected_version:
                    return (
                        False,
                        f"Phiên bản trong manifest.json ({manifest_ver}) không khớp phiên bản khai báo ({expected_version}).",
                        manifest,
                    )
    except (zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return False, f"Lỗi đọc nội dung ZIP / manifest.json: {exc}", {}

    return True, "OK", manifest


def safe_extract_zip(zip_path: Path, dest_dir: Path) -> None:
    """Safely extracts a validated ZIP archive into dest_dir."""
    ok, reason, _ = validate_zip_archive(zip_path)
    if not ok:
        raise ValueError(reason)

    dest_root = dest_dir.resolve()
    dest_root.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            rel_name = info.filename.replace("\\", "/")
            if not rel_name or rel_name.endswith("/"):
                target_dir = (dest_root / rel_name).resolve()
                if not str(target_dir).startswith(str(dest_root)):
                    raise ValueError(f"Unsafe directory path: {info.filename}")
                target_dir.mkdir(parents=True, exist_ok=True)
                continue

            target_path = (dest_root / rel_name).resolve()
            if not str(target_path).startswith(str(dest_root)):
                raise ValueError(f"Unsafe file path: {info.filename}")
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, target_path.open("wb") as dst:
                while True:
                    chunk = src.read(65536)
                    if not chunk:
                        break
                    dst.write(chunk)
