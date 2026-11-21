"""
Script 2: Test & Run Parcel Locker Camera Scanner [Person 1 - Quốc].
- Mode 'test': Reads parcel waybill image from disk (default: edge/test/cameras/shopee.jpg).
- Mode 'raspberry': Captures live video from Raspberry Pi CSI Camera (Picamera2 / GStreamer) or V4L2 camera.
Uses pyzbar to extract tracking_number (mã vận đơn) and PaddleOCR to extract weight (khối lượng: 2,667g).
Prints the extracted result as formatted JSON.
"""
import argparse
import json
import os
import sys

# Ensure project root is in sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from edge.config import DEFAULT_TEST_CAMERA_IMAGE, CAMERA_INDEX, SCAN_TIMEOUT_SECONDS
from edge.cv.scanner import PackageScanner


def main():
    parser = argparse.ArgumentParser(
        description="Quét mã vận đơn (pyzbar) và khối lượng (PaddleOCR) từ ảnh test hoặc Camera CSI Raspberry Pi."
    )
    parser.add_argument(
        "--mode",
        choices=["test", "raspberry"],
        default="test",
        help="Chế độ chạy: 'test' (đọc từ file ảnh trong edge/test/cameras) hoặc 'raspberry' (chạy thực tế với Camera CSI trên Raspberry Pi)",
    )
    parser.add_argument(
        "--image",
        default=DEFAULT_TEST_CAMERA_IMAGE,
        help="Đường dẫn ảnh khi chạy ở chế độ 'test' (mặc định: edge/test/cameras/shopee.jpg)",
    )
    parser.add_argument(
        "--camera-index",
        type=int,
        default=CAMERA_INDEX,
        help="Chỉ số camera khi chạy thực tế (mặc định: 0)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=SCAN_TIMEOUT_SECONDS,
        help="Thời gian chờ quét camera tối đa (giây) ở chế độ 'raspberry'",
    )
    args = parser.parse_args()

    scanner = PackageScanner(
        camera_index=args.camera_index,
        mock_mode=(args.mode == "test"),
        mode=args.mode,
        test_image_path=args.image,
        use_csi=True,
    )

    image_arg = args.image if args.mode == "test" else None
    result = scanner.scan_to_json_dict(image_path=image_arg, timeout=args.timeout)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

