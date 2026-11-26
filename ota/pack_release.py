#!/usr/bin/env python3
"""
Admin Release Packager for Smart Parcel Locker OTA Updates.
Creates a clean `release-v<version>.zip` ready to upload on the Admin OTA Dashboard.

Usage:
  python ota/pack_release.py --version 1.1.0 --changelog "Cập nhật giao diện & sửa lỗi Face ID"
  python ota/pack_release.py --version 1.2.0 --broken   # Tạo gói lỗi giả lập để demo Auto-Rollback
"""
import argparse
import json
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INCLUDE_DIRS = ("server", "edge", "web", "contracts")
EXCLUDE_PARTS = {
    ".venv",
    "__pycache__",
    ".git",
    "ota_storage",
    "logs",
    "certs",
    "models",  # Keep heavy ONNX/Paddle models persistent outside ZIP
    ".pytest_cache",
}
EXCLUDE_FILES = {
    ".env",
    "parcel_locker.db",
    "parcel_locker.db-journal",
    "parcel_locker.db-wal",
}


def build_release_zip(version: str, changelog: str, output_path: Path, broken: bool = False) -> Path:
    manifest = {
        "app_name": "smart-parcel-locker",
        "version": version,
        "changelog": changelog,
        "components": ["server", "edge", "web", "contracts"],
        "health_check": {
            "url": "http://127.0.0.1:8000/health",
            "expect_version": version,
        },
        "db_migration": False,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        zf.writestr("VERSION", f"{'BROKEN-VERSION' if broken else version}\n")
        zf.writestr("CHANGELOG.md", f"# v{version}\n\n{changelog}\n")

        for top_dir in INCLUDE_DIRS:
            src_dir = REPO_ROOT / top_dir
            if not src_dir.is_dir():
                continue
            for file_path in src_dir.rglob("*"):
                if not file_path.is_file():
                    continue
                rel = file_path.relative_to(REPO_ROOT)
                if any(part in EXCLUDE_PARTS for part in rel.parts):
                    continue
                if file_path.name in EXCLUDE_FILES or file_path.suffix in (".pyc", ".pyo", ".db"):
                    continue
                zf.write(file_path, arcname=rel.as_posix())

    return output_path


def main():
    parser = argparse.ArgumentParser(description="Package Smart Parcel Locker OTA release ZIP")
    parser.add_argument("--version", required=True, help="Release version, e.g. 1.1.0")
    parser.add_argument("--changelog", default="Cập nhật phần mềm OTA", help="Release notes")
    parser.add_argument("--out", default=None, help="Output ZIP path (default: dist/release-v<ver>.zip)")
    parser.add_argument("--broken", action="store_true", help="Create a broken package for rollback demo")
    args = parser.parse_args()

    clean_ver = args.version.strip().lstrip("vV")
    out_path = Path(args.out) if args.out else (REPO_ROOT / "dist" / f"release-v{clean_ver}.zip")
    result = build_release_zip(clean_ver, args.changelog, out_path, broken=args.broken)
    size_kb = result.stat().st_size / 1024
    print(f"✅ Đã đóng gói thành công: {result} ({size_kb:.1f} KB)")
    if args.broken:
        print("⚠️ Gói này cố tình đặt VERSION sai để demo tính năng tự động Rollback!")


if __name__ == "__main__":
    main()
