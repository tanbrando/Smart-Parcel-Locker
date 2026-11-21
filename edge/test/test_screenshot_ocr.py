"""
Script 1: Test & Run Shopee Order Screenshot OCR Extraction [Person 1 - Quốc].
Uses PaddleOCR to extract:
- tracking_number (Mã vận chuyển sau 'Thông tin vận chuyển' -> 'SPX Express: SPXVN06152353863A')
- recipient_name (Tên người nhận sau 'Địa chỉ nhận hàng' -> 'Trần Hữu Quốc')
- recipient_phone (Số điện thoại -> '(+84) 911 547 697')
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

from edge.config import DEFAULT_TEST_SCREENSHOT_IMAGE
from edge.cv.ocr_utils import extract_shopee_screenshot


def main():
    parser = argparse.ArgumentParser(
        description="Trích xuất thông tin đơn hàng chụp màn hình Shopee bằng PaddleOCR và in ra JSON."
    )
    parser.add_argument(
        "--image",
        default=DEFAULT_TEST_SCREENSHOT_IMAGE,
        help="Đường dẫn tới file ảnh chụp màn hình đơn hàng (mặc định: edge/test/screenshots/shopee.jpg)",
    )
    args = parser.parse_args()

    result = extract_shopee_screenshot(args.image)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

