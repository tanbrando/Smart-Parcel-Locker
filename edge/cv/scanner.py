"""
Package Scanner Module [Person 1 - Quốc].
Handles camera frame capture (supporting Test Image mode and Raspberry Pi CSI / USB Camera mode),
1D/2D Barcode & QR decoding (pyzbar), and lightweight PaddleOCR weight extraction on parcel labels.
"""
import os
import time
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

import numpy as np

from contracts.schemas import ScanResult
from contracts.mock_data import MOCK_SCAN_VALID_SPX
from edge.config import (
    CAMERA_INDEX,
    CAMERA_FRAME_WIDTH,
    CAMERA_FRAME_HEIGHT,
    CAMERA_MODE,
    USE_CSI_CAMERA,
    DEFAULT_TEST_CAMERA_IMAGE,
    MOCK_HARDWARE,
    SCAN_TIMEOUT_SECONDS,
)
from edge.cv.ocr_utils import (
    extract_tracking_number,
    extract_weight_grams,
    extract_weight_text,
    run_ocr_lines,
)

logger = logging.getLogger("edge.cv.scanner")

try:
    import cv2
    from pyzbar import pyzbar
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False


def build_gstreamer_csi_pipeline(
    sensor_id: int = 0,
    capture_width: int = CAMERA_FRAME_WIDTH,
    capture_height: int = CAMERA_FRAME_HEIGHT,
    framerate: int = 30,
    flip_method: int = 0,
) -> str:
    """
    Constructs a GStreamer pipeline string for Raspberry Pi CSI Camera (libcamerasrc / v4l2).
    """
    return (
        f"libcamerasrc ! video/x-raw, width=(int){capture_width}, height=(int){capture_height}, "
        f"framerate=(fraction){framerate}/1 ! videoconvert ! videoscale ! "
        f"video/x-raw, format=(string)BGR ! appsink drop=true"
    )


class PackageScanner:
    """
    Captures parcel label image (from test image in 'test' mode or Raspberry Pi CSI/USB camera in 'raspberry' mode),
    decodes QR/Barcode via pyzbar to get tracking_number, and runs PaddleOCR to extract weight.
    """

    def __init__(
        self,
        camera_index: int = CAMERA_INDEX,
        mock_mode: bool = MOCK_HARDWARE,
        mode: Optional[str] = None,
        test_image_path: str = DEFAULT_TEST_CAMERA_IMAGE,
        use_csi: bool = USE_CSI_CAMERA,
    ):
        self.camera_index = camera_index
        self.mock_mode = mock_mode or not OPENCV_AVAILABLE
        # Determine operating mode: "test" (static image) or "raspberry" (live CSI/V4L2 camera)
        if mode is not None:
            self.mode = mode.lower()
        else:
            self.mode = "test" if self.mock_mode else CAMERA_MODE
        self.test_image_path = test_image_path
        self.use_csi = use_csi
        self._cap = None
        self._picam2 = None

        logger.info(
            "PackageScanner initialized (mode=%s, mock_mode=%s, camera_index=%d)",
            self.mode,
            self.mock_mode,
            self.camera_index,
        )

    def _open_camera(self):
        """
        Opens physical camera on Raspberry Pi:
        1. Tries Picamera2 (official Raspberry Pi CSI camera stack) if use_csi is True.
        2. Tries GStreamer libcamerasrc CSI pipeline via OpenCV.
        3. Falls back to standard V4L2 / USB camera index via cv2.VideoCapture.
        """
        if not OPENCV_AVAILABLE:
            return

        if self.use_csi:
            try:
                # pyrefly: ignore[missing-import]
                from picamera2 import Picamera2
                if self._picam2 is None:
                    self._picam2 = Picamera2()
                    config = self._picam2.create_preview_configuration(
                        main={"size": (CAMERA_FRAME_WIDTH, CAMERA_FRAME_HEIGHT), "format": "RGB888"}
                    )
                    self._picam2.configure(config)
                    self._picam2.start()
                    logger.info("Opened Raspberry Pi CSI camera via Picamera2.")
                    return
            except Exception as exc:
                logger.debug("Picamera2 not available (%s), trying OpenCV GStreamer/V4L2...", exc)

        if self._cap is None or not self._cap.isOpened():
            if self.use_csi and os.name != "nt":
                gst_pipeline = build_gstreamer_csi_pipeline()
                cap = cv2.VideoCapture(gst_pipeline, cv2.CAP_GSTREAMER)
                if cap.isOpened():
                    self._cap = cap
                    logger.info("Opened Raspberry Pi CSI camera via GStreamer libcamerasrc.")
                    return

            # Standard V4L2 / USB webcam fallback
            self._cap = cv2.VideoCapture(self.camera_index)
            if self._cap.isOpened():
                self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_FRAME_WIDTH)
                self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_FRAME_HEIGHT)
                logger.info("Opened camera index %d via OpenCV VideoCapture.", self.camera_index)

    def _read_camera_frame(self) -> Optional[np.ndarray]:
        """Reads a single BGR frame from active Raspberry Pi CSI or V4L2 camera."""
        if self._picam2 is not None:
            try:
                rgb_frame = self._picam2.capture_array()
                if rgb_frame is not None:
                    return cv2.cvtColor(rgb_frame, cv2.COLOR_RGB2BGR)
            except Exception as exc:
                logger.error("Error capturing from Picamera2: %s", exc)
                return None

        if self._cap is not None and self._cap.isOpened():
            ret, frame = self._cap.read()
            if ret and frame is not None:
                return frame
        return None

    def _release_camera(self):
        if self._picam2 is not None:
            try:
                self._picam2.stop()
                self._picam2.close()
            except Exception:
                pass
            self._picam2 = None

        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def decode_waybill_frame(self, frame: np.ndarray, run_ocr_for_weight: bool = True) -> ScanResult:
        """
        Processes a single image frame:
        1. Uses pyzbar to decode QR Code / Barcode for the tracking number.
        2. Uses PaddleOCR to read the parcel weight (e.g., 'Khối lượng tối đa: 2,667g') from the label text.
        """
        tracking_number: Optional[str] = None
        barcode_type: Optional[str] = None
        raw_barcode_data: str = ""

        # Step 1: Decode Barcode / QR Code with pyzbar
        decoded_objects = pyzbar.decode(frame)
        if not decoded_objects:
            # Try preprocessing (grayscale + upscale) if barcode/QR is small
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            for scale in (1.5, 2.0):
                resized = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
                decoded_objects = pyzbar.decode(resized)
                if decoded_objects:
                    break

        for obj in decoded_objects:
            raw_data = obj.data.decode("utf-8", errors="ignore").strip()
            if raw_data:
                raw_barcode_data = raw_data
                barcode_type = obj.type
                tracking_number = extract_tracking_number(raw_data) or raw_data.upper()
                logger.info("pyzbar decoded %s: %s", barcode_type, tracking_number)
                break

        # Step 2: Run OCR on label to extract declared weight (and fallback tracking number if needed)
        declared_weight = extract_weight_grams(raw_barcode_data)
        raw_text_lines = [raw_barcode_data] if raw_barcode_data else []

        if run_ocr_for_weight and declared_weight is None:
            try:
                ocr_lines = run_ocr_lines(frame)
                raw_text_lines.extend(ocr_lines)
                full_ocr_text = "\n".join(ocr_lines)
                declared_weight = extract_weight_grams(full_ocr_text)
                if not tracking_number:
                    tracking_number = extract_tracking_number(full_ocr_text)
            except Exception as exc:
                logger.warning("OCR weight extraction skipped or failed: %s", exc)

        combined_raw_text = "\n".join(line for line in raw_text_lines if line)
        confidence = 0.99 if tracking_number else 0.0

        return ScanResult(
            tracking_number=tracking_number,
            raw_text=combined_raw_text,
            barcode_type=barcode_type,
            weight_declared=declared_weight,
            confidence=confidence,
            timestamp=datetime.now(timezone.utc),
        )

    def scan_from_image(self, image_path: Optional[str] = None) -> ScanResult:
        """
        Test mode helper: loads waybill image from disk and extracts tracking number (pyzbar) + weight (PaddleOCR).
        """
        target_path = image_path or self.test_image_path
        if not OPENCV_AVAILABLE or not os.path.exists(target_path):
            logger.warning("Image %s not found or OpenCV unavailable. Returning mock scan.", target_path)
            return MOCK_SCAN_VALID_SPX

        frame = cv2.imread(target_path)
        if frame is None:
            raise ValueError(f"Unable to read image file: {target_path}")

        return self.decode_waybill_frame(frame, run_ocr_for_weight=True)

    def scan_package_label(
        self,
        timeout: float = SCAN_TIMEOUT_SECONDS,
        image_path: Optional[str] = None,
    ) -> ScanResult:
        """
        Main scanning entrypoint:
        - If mode == 'test' (or image_path is provided): reads from static image file.
        - If mode == 'raspberry' / 'live': captures frames from Raspberry Pi CSI / USB camera
          until a valid QR/Barcode is decoded by pyzbar, then extracts weight via OCR.
        """
        if image_path is not None or self.mode == "test":
            if self.mock_mode and image_path is None and not os.path.exists(self.test_image_path):
                logger.info("[Mock Scanner] Returning default mock scan result.")
                return MOCK_SCAN_VALID_SPX
            return self.scan_from_image(image_path or self.test_image_path)

        # Live Raspberry Pi CSI / USB camera mode
        self._open_camera()
        if self._picam2 is None and (self._cap is None or not self._cap.isOpened()):
            logger.warning("Failed to open physical camera on Raspberry Pi. Falling back to test image / mock.")
            if os.path.exists(self.test_image_path):
                return self.scan_from_image(self.test_image_path)
            return MOCK_SCAN_VALID_SPX

        start_time = time.time()
        try:
            while (time.time() - start_time) < timeout:
                frame = self._read_camera_frame()
                if frame is None:
                    time.sleep(0.05)
                    continue

                # Fast check with pyzbar on each camera frame
                decoded_objects = pyzbar.decode(frame)
                if decoded_objects:
                    # Once barcode/QR is found, run full decode + OCR weight on that frame
                    return self.decode_waybill_frame(frame, run_ocr_for_weight=True)

                time.sleep(0.05)
        finally:
            self._release_camera()

        logger.warning("Scanning timed out after %.1fs without finding a valid code.", timeout)
        return ScanResult(
            tracking_number=None,
            raw_text="",
            barcode_type=None,
            weight_declared=None,
            success=False,
            error_code="TIMEOUT",
            confidence=0.0,
            timestamp=datetime.now(timezone.utc),
        )

    def scan_to_json_dict(
        self,
        image_path: Optional[str] = None,
        timeout: float = SCAN_TIMEOUT_SECONDS,
    ) -> Dict[str, Any]:
        """
        Returns clean JSON-serializable dict containing tracking_number and weight
        as required by the Edge CV module deliverable.
        """
        res = self.scan_package_label(timeout=timeout, image_path=image_path)
        weight_raw = extract_weight_text(res.raw_text)
        return {
            "tracking_number": res.tracking_number,
            "weight_grams": res.weight_declared,
            "weight_text": weight_raw or (f"{int(res.weight_declared)}g" if res.weight_declared else None),
        }
