"""
Unit & Integration Tests for OTA Software Update (Service + Standalone Agent).
Verifies:
- Safe ZIP validation (Zip Slip / path traversal rejection, manifest version check)
- SHA-256 hashing & HMAC release signature verification
- Successful OTA update (1.0.0 -> 1.1.0)
- Automatic rollback on failed health check (1.1.0 -> 1.2.0 broken -> rolled back to 1.1.0)
- Tampered package rejection without disturbing active release
"""
import json
import tempfile
import zipfile
from pathlib import Path

from ota.agent import OTAAgent
from server.services.ota_service import (
    compute_file_sha256,
    sign_release_hash,
    validate_zip_archive,
    verify_release_signature,
)


def _make_release_zip(zip_path: Path, version: str, extra_files=None):
    manifest = {"app_name": "smart-parcel-locker", "version": version}
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("VERSION", f"{version}\n")
        zf.writestr("server/app_marker.txt", f"release-{version}\n")
        if extra_files:
            for name, content in extra_files.items():
                zf.writestr(name, content)


def test_zip_validation_and_zip_slip_rejection():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        # 1. Valid ZIP
        good_zip = tmp_dir / "good.zip"
        _make_release_zip(good_zip, "1.1.0")
        ok, reason, manifest = validate_zip_archive(good_zip, expected_version="1.1.0")
        assert ok is True, reason
        assert manifest["version"] == "1.1.0"

        # 2. Version mismatch
        ok_ver, _, _ = validate_zip_archive(good_zip, expected_version="2.0.0")
        assert ok_ver is False

        # 3. Path traversal (Zip Slip)
        evil_zip = tmp_dir / "evil.zip"
        _make_release_zip(evil_zip, "1.1.0", extra_files={"../../etc/passwd": "pwned"})
        ok_evil, reason_evil, _ = validate_zip_archive(evil_zip)
        assert ok_evil is False
        assert "path traversal" in reason_evil.lower()


def test_sha256_and_signature_verification():
    with tempfile.TemporaryDirectory() as tmp:
        z = Path(tmp) / "rel.zip"
        _make_release_zip(z, "1.1.0")
        digest = compute_file_sha256(z)
        sig = sign_release_hash(digest, "1.1.0", secret="test-secret")
        assert verify_release_signature(digest, "1.1.0", sig, secret="test-secret") is True
        assert verify_release_signature(digest, "1.1.1", sig, secret="test-secret") is False
        assert verify_release_signature(digest, "1.1.0", "bad-sig", secret="test-secret") is False


def test_agent_update_and_auto_rollback():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "ota_base"
        zips_dir = Path(tmp) / "server_zips"
        zips_dir.mkdir(parents=True)

        # Seed initial release 1.0.0
        rel_100 = base / "releases" / "1.0.0"
        rel_100.mkdir(parents=True)
        (rel_100 / "VERSION").write_text("1.0.0\n", encoding="utf-8")

        statuses = []
        health_behavior = {"pass": True}

        agent = OTAAgent(
            server_url="http://127.0.0.1:8000",
            agent_key="k",
            signing_key="test-secret",
            base_dir=base,
            restart_fn=lambda: True,
            health_check_fn=lambda ver, timeout: health_behavior["pass"],
        )
        agent.switch_current_symlink(rel_100)
        agent.report_status = lambda jid, st, prog, msg: statuses.append((jid, st, prog, msg))

        # --- 1. Successful update 1.0.0 -> 1.1.0 ---
        zip_110 = zips_dir / "release-v1.1.0.zip"
        _make_release_zip(zip_110, "1.1.0")
        sha_110 = compute_file_sha256(zip_110)
        sig_110 = sign_release_hash(sha_110, "1.1.0", secret="test-secret")
        agent._download_zip = lambda path, ver: zips_dir / f"release-v{ver}.zip"

        res1 = agent.process_job(
            {
                "job_id": 1,
                "action": "UPDATE",
                "target_version": "1.1.0",
                "download_path": "/mock/1.1.0",
                "sha256": sha_110,
                "signature": sig_110,
            }
        )
        assert res1 == "SUCCESS"
        assert (agent.current_link / "VERSION").read_text(encoding="utf-8").strip() == "1.1.0"

        # --- 2. Tampered signature rejected without changing current (stays 1.1.0) ---
        zip_bad = zips_dir / "release-v1.1.9.zip"
        _make_release_zip(zip_bad, "1.1.9")
        sha_bad = compute_file_sha256(zip_bad)
        res_tamper = agent.process_job(
            {
                "job_id": 2,
                "action": "UPDATE",
                "target_version": "1.1.9",
                "download_path": "/mock/1.1.9",
                "sha256": sha_bad,
                "signature": "forged-signature",
            }
        )
        assert res_tamper == "FAILED"
        assert (agent.current_link / "VERSION").read_text(encoding="utf-8").strip() == "1.1.0"

        # --- 3. Broken release 1.2.0 fails health check -> auto rollback to 1.1.0 ---
        zip_120 = zips_dir / "release-v1.2.0.zip"
        _make_release_zip(zip_120, "1.2.0")
        sha_120 = compute_file_sha256(zip_120)
        sig_120 = sign_release_hash(sha_120, "1.2.0", secret="test-secret")
        health_behavior["pass"] = False

        res_rb = agent.process_job(
            {
                "job_id": 3,
                "action": "UPDATE",
                "target_version": "1.2.0",
                "download_path": "/mock/1.2.0",
                "sha256": sha_120,
                "signature": sig_120,
            }
        )
        assert res_rb == "ROLLED_BACK"
        assert (agent.current_link / "VERSION").read_text(encoding="utf-8").strip() == "1.1.0"


if __name__ == "__main__":
    tests = [
        test_zip_validation_and_zip_slip_rejection,
        test_sha256_and_signature_verification,
        test_agent_update_and_auto_rollback,
    ]
    print(f"Running {len(tests)} OTA Software Update tests...\n")
    for fn in tests:
        fn()
        print(f"  [PASS] {fn.__name__}")
    print("\nAll OTA tests passed successfully!")
