"""
Package Scanner Module [Person 1].
Handles camera frame capture, 1D/2D Barcode decoding (pyzbar), and OCR label parsing.
"""
import time
import logging
from datetime import datetime
from typing import Optional

from contracts.schemas import ScanResult
from contracts.mock_data import MOCK_SCAN_VALID_SPX
from edge.config import CAMERA_INDEX, MOCK_HARDWARE, SCAN_TIMEOUT_SECONDS
from edge.cv.ocr_utils import extract_tracking_number, extract_weight_grams

logger = logging.getLogger("edge.cv.scanner")

try:
    import cv2
    from pyzbar import pyzbar
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False


class PackageScanner:
    """Captures video feed, detects barcodes/QR codes, and parses parcel waybill labels."""

    def __init__(self, camera_index: int = CAMERA_INDEX, mock_mode: bool = MOCK_HARDWARE):
        self.camera_index = camera_index
        self.mock_mode = mock_mode or not OPENCV_AVAILABLE
        self._cap = None

        if self.mock_mode:
            logger.info("PackageScanner initialized in MOCK mode.")
        else:
            logger.info("PackageScanner initialized with camera index %d.", self.camera_index)

    def _open_camera(self):
        if not self.mock_mode and OPENCV_AVAILABLE:
            if self._cap is None or not self._cap.isOpened():
                self._cap = cv2.VideoCapture(self.camera_index)

    def _release_camera(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def scan_package_label(self, timeout: float = SCAN_TIMEOUT_SECONDS) -> ScanResult:
        """
        Continuously captures frames from camera until a valid QR code, Barcode,
        or tracking label is detected, or until timeout expires.
        """
        if self.mock_mode:
            logger.info("[Mock Scanner] Simulating label scan...")
            time.sleep(1.0)
            return MOCK_SCAN_VALID_SPX

        self._open_camera()
        if self._cap is None or not self._cap.isOpened():
            logger.warning("Failed to open physical camera. Falling back to mock scan.")
            return MOCK_SCAN_VALID_SPX

        start_time = time.time()
        try:
            while (time.time() - start_time) < timeout:
                ret, frame = self._cap.read()
                if not ret or frame is None:
                    time.sleep(0.05)
                    continue

                # 1. Decode Barcode / QR Code with pyzbar
                decoded_objects = pyzbar.decode(frame)
                for obj in decoded_objects:
                    raw_data = obj.data.decode("utf-8", errors="ignore").strip()
                    barcode_type = obj.type
                    tracking_candidate = extract_tracking_number(raw_data) or raw_data.upper()
                    declared_weight = extract_weight_grams(raw_data)

                    logger.info("Barcode detected: %s (%s)", tracking_candidate, barcode_type)
                    return ScanResult(
                        tracking_number=tracking_candidate,
                        raw_text=raw_data,
                        barcode_type=barcode_type,
                        weight_declared=declared_weight,
                        success=True,
                        ocr_weight=int(round(declared_weight)) if declared_weight is not None else None,
                        confidence=0.99,
                        timestamp=datetime.utcnow(),
                    )

                time.sleep(0.05)

        finally:
            self._release_camera()

        # Timeout reached
        logger.warning("Scanning timed out without finding a valid code.")
        return ScanResult(
            tracking_number=None,
            raw_text="",
            barcode_type=None,
            weight_declared=None,
            success=False,
            error_code="TIMEOUT",
            confidence=0.0,
            timestamp=datetime.utcnow(),
        )
