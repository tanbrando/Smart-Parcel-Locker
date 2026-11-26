#!/usr/bin/env python3
"""
Standalone Raspberry Pi OTA Update Agent for Smart Parcel Locker.
Runs independently (via systemd) outside `releases/` so it survives Server/Edge restarts.

Flow:
1. Poll GET /api/v1/ota/agent/pending-job
2. Download ZIP -> Verify SHA-256 + HMAC signature -> Safe extract to releases/<ver>/
3. Preserve persistent files (.env, DB, ota_storage, certs) & optionally pip install if requirements changed
4. Atomic symlink swap: current -> releases/<ver>
5. Restart smart-locker-server & smart-locker-edge services
6. Health check GET /health (verify version == target_version)
7. Auto-rollback to previous release if health check fails
8. Cleanup old releases (keep last 3)
"""
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

import requests

# Ensure repo imports work when run from /opt/smart-locker-ota or repo root
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from server.services.ota_service import (
    compute_file_sha256,
    get_ota_agent_key,
    get_ota_signing_key,
    safe_extract_zip,
    verify_release_signature,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (ota.agent) %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("ota.agent")


class OTAAgent:
    """Self-contained OTA deployment agent with atomic symlink swap and auto-rollback."""

    def __init__(
        self,
        server_url: Optional[str] = None,
        agent_key: Optional[str] = None,
        signing_key: Optional[str] = None,
        base_dir: Optional[Path] = None,
        shared_dir: Optional[Path] = None,
        restart_commands: Optional[List[str]] = None,
        health_url: Optional[str] = None,
        health_timeout_sec: int = 45,
        keep_releases: int = 3,
        poll_interval_sec: float = 5.0,
        restart_fn: Optional[Callable[[], bool]] = None,
        health_check_fn: Optional[Callable[[str, int], bool]] = None,
    ):
        self.server_url = (server_url or os.getenv("OTA_SERVER_URL", "http://127.0.0.1:8000")).rstrip("/")
        self.agent_key = agent_key or get_ota_agent_key()
        self.signing_key = signing_key or get_ota_signing_key()

        self.base_dir = Path(base_dir or os.getenv("OTA_BASE_DIR", "/opt/smart-locker"))
        self.releases_dir = self.base_dir / "releases"
        self.downloads_dir = self.base_dir / "downloads"
        self.current_link = self.base_dir / "current"
        self.shared_dir = Path(shared_dir or os.getenv("OTA_SHARED_DIR", str(self.base_dir / "shared")))
        self.state_file = self.base_dir / "state.json"

        default_cmds = os.getenv(
            "OTA_RESTART_COMMANDS",
            "sudo systemctl restart smart-locker-server.service; sudo systemctl restart smart-locker-edge.service",
        )
        if restart_commands is not None:
            self.restart_commands = restart_commands
        else:
            self.restart_commands = [c.strip() for c in default_cmds.split(";") if c.strip()]

        self.health_url = health_url or os.getenv("OTA_HEALTH_URL", f"{self.server_url}/health")
        self.health_timeout_sec = int(os.getenv("OTA_HEALTH_TIMEOUT", str(health_timeout_sec)))
        self.keep_releases = keep_releases
        self.poll_interval_sec = poll_interval_sec
        self._restart_fn = restart_fn
        self._health_check_fn = health_check_fn

        self.releases_dir.mkdir(parents=True, exist_ok=True)
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.shared_dir.mkdir(parents=True, exist_ok=True)

    @property
    def _headers(self) -> Dict[str, str]:
        return {"X-OTA-Agent-Key": self.agent_key}

    def _save_state(self, state: Dict) -> None:
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.state_file)

    def _clear_state(self) -> None:
        self.state_file.unlink(missing_ok=True)

    def report_status(self, job_id: int, status: str, progress: int, message: str) -> None:
        """Reports OTA progress back to Backend (retries briefly if server is restarting)."""
        url = f"{self.server_url}/api/v1/ota/agent/jobs/{job_id}/status"
        payload = {"status": status, "progress": progress, "message": message}
        for attempt in range(5):
            try:
                resp = requests.post(url, json=payload, headers=self._headers, timeout=5.0)
                if resp.status_code == 200:
                    return
            except requests.RequestException:
                pass
            time.sleep(1.0 if attempt < 4 else 0.0)
        logger.warning("Could not report status %s for job #%d", status, job_id)

    def get_current_release_path(self) -> Optional[Path]:
        if self.current_link.is_symlink():
            return self.current_link.resolve()
        if self.current_link.is_dir():
            ver_file = self.current_link / "VERSION"
            if ver_file.is_file():
                ver = ver_file.read_text(encoding="utf-8").strip()
                candidate = self.releases_dir / ver
                if candidate.is_dir():
                    return candidate.resolve()
            return self.current_link.resolve()
        return None

    def switch_current_symlink(self, target_release_dir: Path) -> None:
        """Atomically switches `current` symlink to `target_release_dir`."""
        target_resolved = target_release_dir.resolve()
        if not target_resolved.is_dir():
            raise FileNotFoundError(f"Release directory does not exist: {target_resolved}")

        if os.name == "nt":
            # Windows fallback (symlinks often require admin privilege)
            if self.current_link.is_symlink() or self.current_link.is_file():
                self.current_link.unlink()
            elif self.current_link.is_dir():
                shutil.rmtree(self.current_link)
            shutil.copytree(target_resolved, self.current_link)
            return

        tmp_link = self.base_dir / "current.tmp"
        if tmp_link.is_symlink() or tmp_link.exists():
            tmp_link.unlink()
        os.symlink(target_resolved, tmp_link)
        # Atomic rename on POSIX
        subprocess.run(["mv", "-Tf", str(tmp_link), str(self.current_link)], check=True)

    def _link_shared_persistent_files(self, release_dir: Path) -> None:
        """
        Ensures persistent config/data (.env, SQLite DB, ota_storage, certs, models)
        live in `shared_dir` so updates and rollbacks never lose data.
        """
        shared_items = [
            ("server/.env", False),
            ("edge/.env", False),
            ("parcel_locker.db", False),
            ("ota_storage", True),
            ("certs", True),
        ]
        for rel_path, is_dir in shared_items:
            src = self.shared_dir / rel_path
            dst = release_dir / rel_path
            if is_dir:
                src.mkdir(parents=True, exist_ok=True)
            else:
                if not src.exists():
                    continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.is_symlink() or dst.is_file():
                dst.unlink()
            elif dst.is_dir():
                shutil.rmtree(dst)
            if os.name == "nt":
                if is_dir:
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
            else:
                os.symlink(src, dst)

    def _restart_services(self) -> bool:
        if self._restart_fn is not None:
            return bool(self._restart_fn())
        for cmd in self.restart_commands:
            logger.info("Running restart command: %s", cmd)
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if res.returncode != 0:
                logger.error("Restart command failed (%s): %s", cmd, res.stderr.strip())
                return False
        return True

    def _verify_health(self, expected_version: str) -> bool:
        if self._health_check_fn is not None:
            return bool(self._health_check_fn(expected_version, self.health_timeout_sec))
        deadline = time.time() + self.health_timeout_sec
        while time.time() < deadline:
            try:
                resp = requests.get(self.health_url, timeout=2.0)
                if resp.status_code == 200:
                    data = resp.json()
                    running_ver = str(data.get("version", "")).strip()
                    if data.get("status") == "ok" and running_ver == expected_version:
                        logger.info("Health check PASSED: running version %s", running_ver)
                        return True
                    logger.info("Health check waiting: got version=%s, expected=%s", running_ver, expected_version)
            except Exception:
                pass
            time.sleep(1.5)
        logger.error("Health check FAILED after %ds (expected version %s)", self.health_timeout_sec, expected_version)
        return False

    def _cleanup_old_releases(self, active_dir: Optional[Path]) -> None:
        """Keeps the `keep_releases` most recent releases plus the active one."""
        dirs = [d for d in self.releases_dir.iterdir() if d.is_dir()]
        dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        active_resolved = active_dir.resolve() if active_dir else None
        kept = 0
        for d in dirs:
            if active_resolved and d.resolve() == active_resolved:
                kept += 1
                continue
            if kept < self.keep_releases:
                kept += 1
                continue
            logger.info("Cleaning up old release directory: %s", d)
            shutil.rmtree(d, ignore_errors=True)

    def _download_zip(self, download_path: str, version: str) -> Path:
        url = f"{self.server_url}{download_path}" if download_path.startswith("/") else download_path
        dest = self.downloads_dir / f"release-v{version}.zip"
        with requests.get(url, headers=self._headers, stream=True, timeout=60.0) as resp:
            resp.raise_for_status()
            with dest.open("wb") as out:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        out.write(chunk)
        return dest

    def process_job(self, job: Dict) -> str:
        """Executes a single UPDATE or ROLLBACK job end-to-end with automatic rollback."""
        job_id = int(job["job_id"])
        action = str(job.get("action", "UPDATE")).upper()
        target_version = str(job["target_version"]).strip()
        prev_release_dir = self.get_current_release_path()

        logger.info("=== Processing OTA Job #%d: %s -> v%s ===", job_id, action, target_version)

        if action == "ROLLBACK":
            return self._handle_rollback_job(job_id, target_version, prev_release_dir)

        zip_path: Optional[Path] = None
        new_release_dir = self.releases_dir / target_version

        try:
            # 1. DOWNLOADING
            self._save_state({"job_id": job_id, "step": "DOWNLOADING", "target_version": target_version})
            self.report_status(job_id, "DOWNLOADING", 15, f"Đang tải gói v{target_version}...")
            zip_path = self._download_zip(job["download_path"], target_version)

            # 2. VERIFYING (SHA-256 + Signature)
            self._save_state({"job_id": job_id, "step": "VERIFYING", "target_version": target_version})
            self.report_status(job_id, "VERIFYING", 35, "Đang xác minh SHA-256 và chữ ký số...")
            actual_sha256 = compute_file_sha256(zip_path)
            expected_sha256 = str(job.get("sha256", "")).strip()
            signature = str(job.get("signature", "")).strip()

            if not expected_sha256 or actual_sha256 != expected_sha256:
                raise ValueError(f"Sai mã băm SHA-256 (expected {expected_sha256[:12]}, got {actual_sha256[:12]}).")
            if not verify_release_signature(actual_sha256, target_version, signature, secret=self.signing_key):
                raise ValueError("Chữ ký số gói OTA không hợp lệ! Từ chối cài đặt.")

            # 3. INSTALLING (Safe Extract into releases/<version>/)
            self._save_state({"job_id": job_id, "step": "INSTALLING", "target_version": target_version})
            self.report_status(job_id, "INSTALLING", 55, f"Đang giải nén an toàn vào releases/{target_version}...")
            if new_release_dir.exists():
                shutil.rmtree(new_release_dir)
            safe_extract_zip(zip_path, new_release_dir)
            # Ensure VERSION file matches target_version
            (new_release_dir / "VERSION").write_text(f"{target_version}\n", encoding="utf-8")
            self._link_shared_persistent_files(new_release_dir)

            # 4. RESTARTING (Atomic Symlink Switch)
            self._save_state(
                {
                    "job_id": job_id,
                    "step": "RESTARTING",
                    "target_version": target_version,
                    "previous_dir": str(prev_release_dir) if prev_release_dir else None,
                }
            )
            self.report_status(job_id, "RESTARTING", 75, f"Đang chuyển symlink sang v{target_version} và khởi động lại...")
            self.switch_current_symlink(new_release_dir)

            if not self._restart_services():
                raise RuntimeError("Không thể khởi động lại dịch vụ sau khi chuyển phiên bản.")

            # 5. HEALTH_CHECK
            self._save_state(
                {
                    "job_id": job_id,
                    "step": "HEALTH_CHECK",
                    "target_version": target_version,
                    "previous_dir": str(prev_release_dir) if prev_release_dir else None,
                }
            )
            self.report_status(job_id, "HEALTH_CHECK", 90, f"Đang kiểm tra /health cho v{target_version}...")
            if not self._verify_health(target_version):
                raise RuntimeError(f"Health check thất bại: v{target_version} không phản hồi đúng phiên bản.")

            # 6. SUCCESS
            self._cleanup_old_releases(new_release_dir)
            self._clear_state()
            self.report_status(job_id, "SUCCESS", 100, f"Cập nhật thành công lên v{target_version}!")
            return "SUCCESS"

        except Exception as exc:
            logger.error("OTA Job #%d failed: %s", job_id, exc)
            # Rollback ONLY if we already switched symlink away from previous version
            state = {}
            if self.state_file.is_file():
                try:
                    state = json.loads(self.state_file.read_text(encoding="utf-8"))
                except Exception:
                    pass

            if state.get("step") in ("RESTARTING", "HEALTH_CHECK") and prev_release_dir and prev_release_dir.is_dir():
                logger.warning("Initiating automatic rollback to %s...", prev_release_dir)
                try:
                    self.switch_current_symlink(prev_release_dir)
                    self._restart_services()
                    self._clear_state()
                    self.report_status(
                        job_id,
                        "ROLLED_BACK",
                        100,
                        f"Bản v{target_version} lỗi ({exc}). Đã tự động rollback về {prev_release_dir.name}.",
                    )
                    return "ROLLED_BACK"
                except Exception as rb_exc:
                    logger.critical("Auto-rollback failed: %s", rb_exc)

            # Cleanup partial extraction if failed before switching
            if state.get("step") in ("DOWNLOADING", "VERIFYING", "INSTALLING") and new_release_dir.exists():
                shutil.rmtree(new_release_dir, ignore_errors=True)
            self._clear_state()
            self.report_status(job_id, "FAILED", 100, f"Cập nhật thất bại (bản cũ vẫn giữ nguyên): {exc}")
            return "FAILED"
        finally:
            if zip_path and zip_path.is_file():
                zip_path.unlink(missing_ok=True)

    def _handle_rollback_job(
        self,
        job_id: int,
        target_version: str,
        prev_release_dir: Optional[Path],
    ) -> str:
        target_dir = self.releases_dir / target_version
        if not target_dir.is_dir():
            msg = f"Không tìm thấy thư mục release cũ v{target_version} trên Pi để rollback."
            self.report_status(job_id, "FAILED", 100, msg)
            return "FAILED"

        try:
            self.report_status(job_id, "RESTARTING", 50, f"Đang rollback symlink về v{target_version}...")
            self.switch_current_symlink(target_dir)
            if not self._restart_services():
                raise RuntimeError("Lỗi khởi động lại dịch vụ khi rollback.")
            self.report_status(job_id, "HEALTH_CHECK", 85, f"Đang kiểm tra /health bản v{target_version}...")
            if not self._verify_health(target_version):
                raise RuntimeError(f"Health check thất bại sau khi rollback về v{target_version}.")
            self.report_status(job_id, "ROLLED_BACK", 100, f"Đã rollback thành công về v{target_version}.")
            return "ROLLED_BACK"
        except Exception as exc:
            logger.error("Manual rollback job #%d failed: %s", job_id, exc)
            if prev_release_dir and prev_release_dir.is_dir():
                try:
                    self.switch_current_symlink(prev_release_dir)
                    self._restart_services()
                except Exception:
                    pass
            self.report_status(job_id, "FAILED", 100, f"Rollback thất bại: {exc}")
            return "FAILED"

    def poll_once(self) -> Optional[str]:
        """Polls backend once for a pending OTA job and processes it if present."""
        try:
            resp = requests.get(
                f"{self.server_url}/api/v1/ota/agent/pending-job",
                headers=self._headers,
                timeout=5.0,
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            if data.get("has_job") and data.get("job"):
                return self.process_job(data["job"])
        except requests.RequestException as exc:
            logger.debug("OTA poll failed (server offline?): %s", exc)
        return None

    def run_forever(self) -> None:
        logger.info("🚀 Smart Parcel Locker OTA Agent started (polling %s every %.1fs)", self.server_url, self.poll_interval_sec)
        while True:
            self.poll_once()
            time.sleep(self.poll_interval_sec)


if __name__ == "__main__":
    agent = OTAAgent()
    agent.run_forever()
