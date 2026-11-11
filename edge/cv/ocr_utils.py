"""
OCR and Text Parsing Utilities [Person 1 - Quốc].
Extracts tracking numbers, recipient details, and declared parcel weights
from order screenshots (Shopee / TikTok) and waybill labels using PaddleOCR & Regex.
"""
import os
import re
import sys
import json
import platform
import subprocess
import tempfile
import unicodedata
import logging
import warnings
from typing import Optional, List, Dict, Any, Union

# Suppress library warnings for clean JSON CLI output
warnings.filterwarnings("ignore")
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["GLOG_minloglevel"] = "3"

import numpy as np

# Set PaddleX models directory to edge/models/paddlex
EDGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.getenv("PADDLE_PDX_CACHE_HOME", os.path.join(EDGE_DIR, "models", "paddlex"))
os.environ["PADDLE_PDX_CACHE_HOME"] = MODELS_DIR

# Disable OneDNN / PIR incompatibilities and network checks in PaddlePaddle 3.x on CPU
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
os.environ.setdefault("DISABLE_MODEL_SOURCE_CHECK", "True")
os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("FLAGS_enable_pir_api", "0")

logger = logging.getLogger("edge.cv.ocr_utils")

# Common Vietnamese and Regional Courier Tracking Regexes
TRACKING_PATTERNS = [
    # Shopee Express (SPX): e.g., SPX038472918VN, SPXVN06152353863A, SPXVN022378345908
    r"\b(SPX[A-Z0-9]{7,16}(?:VN)?)\b",
    # Giao Hang Nhanh (GHN): e.g., GHN78921820, G8X129Y7
    r"\b(GHN[A-Z0-9]{6,12})\b",
    # Giao Hang Tiet Kiem (GHTK): e.g., S22184918.BO.128
    r"\b(S\d{6,10}\.[A-Z0-9\.]+)\b",
    # Viettel Post: e.g., VT892182012
    r"\b(VT[0-9]{8,12})\b",
    # J&T Express: e.g., 841209384712, 855091654687
    r"\b(8[45]\d{10,12})\b",
    # Fallback generic tracking alphanumeric code (8-16 chars)
    r"\b([A-Z]{2,5}\d{7,14}[A-Z0-9]{0,3})\b",
]

# Weight Regex: matches "2,667g", "450g", "0.5 kg", "1.2kg", "Khối lượng tối đa: 2,667g"
WEIGHT_LABEL_PATTERN = re.compile(
    r"(?:tr[oọ]ng\s*l[uư][oợ]ng|kh[oố]i\s*l[uư][oợ]ng|tl\s*t[ií]nh\s*ph[ií]|weight|kl|gw|nw)"
    r"[^:\d]{0,20}[:=\-]?\s*(\d{1,3}(?:[\.,]\d{3})+|\d+(?:[\.,]\d+)?)\s*(kg|kilo|kilogram|g|gr|gram)\b",
    re.IGNORECASE,
)

WEIGHT_FALLBACK_PATTERN = re.compile(
    r"\b(\d{1,3}(?:,\d{3})+|\d+(?:[\.,]\d+)?)\s*(kg|kilo|kilogram|g|gr|gram)\b",
    re.IGNORECASE,
)

# Phone number regex supporting "(+84) 911 547 697", "+84911547697", "0911 547 697"
PHONE_PATTERN = re.compile(
    r"(\(\+?84\)\s*\d[\d\s\.\-]{7,13}\d|\+?84\s*\d[\d\s\.\-]{7,13}\d|\b0\d[\d\s\.\-]{7,12}\d\b)"
)

# Common Vietnamese name syllable restoration when PaddleOCR drops diacritics
VI_NAME_TOKEN_MAP = {
    "trn": "Trần",
    "tran": "Trần",
    "hu": "Hữu",
    "huu": "Hữu",
    "quc": "Quốc",
    "quoc": "Quốc",
    "nguyn": "Nguyễn",
    "nguyen": "Nguyễn",
    "vn": "Văn",
    "van": "Văn",
    "th": "Thị",
    "thi": "Thị",
    "phm": "Phạm",
    "pham": "Phạm",
    "l": "Lê",
    "le": "Lê",
    "đng": "Đặng",
    "dng": "Đặng",
    "bùi": "Bùi",
    "bui": "Bùi",
    "đ": "Đỗ",
    "hoàng": "Hoàng",
    "hoang": "Hoàng",
    "huỳnh": "Huỳnh",
    "huynh": "Huỳnh",
    "ngô": "Ngô",
    "ngo": "Ngô",
    "dương": "Dương",
    "duong": "Dương",
    "lý": "Lý",
}

_OCR_INSTANCE = None
_RAPID_OCR_INSTANCE = None
_PADDLE_CRASHED = False


def get_paddle_ocr():
    """Singleton initializer for lightweight PaddleOCR model."""
    global _OCR_INSTANCE
    if _OCR_INSTANCE is None:
        from paddleocr import PaddleOCR
        logger.info("Initializing PaddleOCR engine (mobile lightweight model)...")
        _OCR_INSTANCE = PaddleOCR(
            text_detection_model_name="PP-OCRv5_mobile_det",
            text_recognition_model_name="latin_PP-OCRv5_mobile_rec",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            enable_mkldnn=False,
        )
    return _OCR_INSTANCE


def _decode_to_bgr(image_input: Union[str, bytes, np.ndarray]) -> np.ndarray:
    """Normalizes file path, raw bytes, or ndarray into a BGR OpenCV image."""
    import cv2

    if isinstance(image_input, bytes):
        nparr = np.frombuffer(image_input, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Could not decode image bytes for OCR.")
        return img
    if isinstance(image_input, str):
        if not os.path.exists(image_input):
            raise FileNotFoundError(f"Image not found: {image_input}")
        img = cv2.imread(image_input)
        if img is None:
            raise ValueError(f"Unable to read image file: {image_input}")
        return img
    if isinstance(image_input, np.ndarray):
        return image_input
    raise TypeError(f"Unsupported image_input type: {type(image_input)}")


def _run_paddle_lines_in_process(target: Union[str, np.ndarray]) -> List[str]:
    """Runs PaddleOCR directly in the current process."""
    ocr = get_paddle_ocr()
    results = ocr.predict(target)
    if not results:
        return []

    first_res = results[0]
    if isinstance(first_res, dict) and "rec_texts" in first_res:
        return [str(t).strip() for t in first_res["rec_texts"] if str(t).strip()]

    lines = []
    for line in first_res:
        if isinstance(line, (list, tuple)) and len(line) >= 2:
            txt = line[1][0] if isinstance(line[1], (list, tuple)) else str(line[1])
            if txt.strip():
                lines.append(txt.strip())
    return lines


def _run_paddle_lines_isolated(image_input: Union[str, bytes, np.ndarray]) -> List[str]:
    """Runs PaddleOCR in a child process so C++ SIGSEGV never kills the main Server/Edge process."""
    global _PADDLE_CRASHED
    if _PADDLE_CRASHED:
        return []

    import cv2

    tmp_path = None
    target_path = image_input if isinstance(image_input, str) else None
    try:
        if target_path is None:
            img_bgr = _decode_to_bgr(image_input)
            fd, tmp_path = tempfile.mkstemp(suffix=".jpg", prefix="ocr_")
            os.close(fd)
            cv2.imwrite(tmp_path, img_bgr)
            target_path = tmp_path

        repo_root = os.path.dirname(EDGE_DIR)
        worker_code = (
            "import json, sys; "
            "from edge.cv.ocr_utils import _run_paddle_lines_in_process; "
            "lines = _run_paddle_lines_in_process(sys.argv[1]); "
            "print('__OCR_JSON__:' + json.dumps(lines, ensure_ascii=False))"
        )
        env = os.environ.copy()
        env["PYTHONPATH"] = repo_root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        proc = subprocess.run(
            [sys.executable, "-c", worker_code, target_path],
            capture_output=True,
            text=True,
            timeout=25,
            env=env,
        )
        if proc.returncode != 0:
            _PADDLE_CRASHED = True
            logger.warning(
                "PaddleOCR isolated worker exited with code %d; disabling PaddleOCR for this session.",
                proc.returncode,
            )
            return []

        for out_line in reversed(proc.stdout.splitlines()):
            if out_line.startswith("__OCR_JSON__:"):
                return json.loads(out_line.split("__OCR_JSON__:", 1)[1])
        return []
    except Exception as exc:
        logger.warning("Isolated PaddleOCR execution failed: %s", exc)
        return []
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def _run_rapidocr_lines(img_bgr: np.ndarray) -> List[str]:
    """Optional lightweight ONNX OCR fallback via rapidocr_onnxruntime."""
    global _RAPID_OCR_INSTANCE
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        return []

    if _RAPID_OCR_INSTANCE is None:
        logger.info("Initializing RapidOCR ONNX engine...")
        _RAPID_OCR_INSTANCE = RapidOCR()
    res, _ = _RAPID_OCR_INSTANCE(img_bgr)
    if not res:
        return []
    return [str(item[1]).strip() for item in res if len(item) >= 2 and str(item[1]).strip()]


def _run_tesseract_lines(img_bgr: np.ndarray) -> List[str]:
    """Native Tesseract OCR fallback (crash-free on Raspberry Pi ARM64)."""
    try:
        import cv2
        import pytesseract
    except ImportError:
        return []

    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    for lang in ("vie+eng", "eng"):
        try:
            text = pytesseract.image_to_string(rgb, lang=lang)
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            if lines:
                return lines
        except Exception:
            continue
    return []


def run_ocr_lines(image_input: Union[str, bytes, np.ndarray]) -> List[str]:
    """
    Extracts recognized text lines from a file path, image bytes, or BGR ndarray.
    Uses PaddleOCR on x86_64 PCs and crash-safe fallbacks (RapidOCR / Tesseract / isolated Paddle) on ARM/Pi.
    """
    engine = os.getenv("OCR_ENGINE", "auto").strip().lower()
    if engine == "off":
        return []

    img_bgr = _decode_to_bgr(image_input)
    is_arm = platform.machine().lower() in ("aarch64", "arm64", "armv7l", "armv6l")

    if engine == "tesseract":
        return _run_tesseract_lines(img_bgr)
    if engine == "rapidocr":
        return _run_rapidocr_lines(img_bgr)
    if engine == "paddle":
        return _run_paddle_lines_isolated(image_input) if is_arm else _run_paddle_lines_in_process(img_bgr)

    # Auto mode:
    # - On Raspberry Pi (ARM), prioritize native ARM-safe engines first to avoid PaddlePaddle SIGSEGV
    if is_arm:
        for runner in (_run_rapidocr_lines, _run_tesseract_lines):
            lines = runner(img_bgr)
            if lines:
                return lines
        return _run_paddle_lines_isolated(image_input)

    # - On x86_64/AMD64 PC, run PaddleOCR with safe fallback
    try:
        lines = _run_paddle_lines_in_process(img_bgr)
        if lines:
            return lines
    except Exception as exc:
        logger.warning("PaddleOCR failed (%s), trying fallback OCR...", exc)

    for runner in (_run_rapidocr_lines, _run_tesseract_lines):
        lines = runner(img_bgr)
        if lines:
            return lines
    return []


def _strip_accents(s: str) -> str:
    """Removes Vietnamese accents for fuzzy keyword matching."""
    s = s.replace("đ", "d").replace("Đ", "D")
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    ).lower()


def _normalize_vietnamese_name(raw_name: str) -> str:
    """Restores common Vietnamese name diacritics if OCR stripped vowels."""
    cleaned = re.sub(r"^[\W_]+|[\W_]+$", "", raw_name).strip()
    if not cleaned:
        return ""
    tokens = cleaned.split()
    restored = []
    for tok in tokens:
        low = tok.lower()
        if low in VI_NAME_TOKEN_MAP:
            restored.append(VI_NAME_TOKEN_MAP[low])
        else:
            restored.append(tok)
    return " ".join(restored)


def extract_tracking_number(text: str) -> Optional[str]:
    """
    Scans raw text to match courier tracking number patterns.
    Returns normalized uppercase tracking string or None.
    """
    if not text:
        return None

    cleaned = text.strip()

    # Check explicit Shopee Express format "SPX Express: SPXVN06152353863A"
    spx_match = re.search(
        r"(?:SPX\s*Express|M[aãäā]\s*v[aậ]?n\s*[đd][oơ]n)\s*[:\-]?\s*([A-Z0-9]{8,20})",
        cleaned,
        re.IGNORECASE,
    )
    if spx_match:
        return spx_match.group(1).upper()

    for pattern in TRACKING_PATTERNS:
        match = re.search(pattern, cleaned, re.IGNORECASE)
        if match:
            return match.group(1).upper()

    return None


def _parse_number_and_unit_to_grams(num_str: str, unit_str: str) -> Optional[float]:
    unit = unit_str.lower()
    raw = num_str.strip()

    try:
        if unit in ("g", "gr", "gram"):
            # In grams, "2,667g" or "1,500g" uses comma as thousands separator (= 2667g)
            if re.match(r"^\d{1,3}(,\d{3})+$", raw):
                val = float(raw.replace(",", ""))
            else:
                val = float(raw.replace(",", "."))
            return round(val, 2)
        elif unit in ("kg", "kilo", "kilogram"):
            val = float(raw.replace(",", "."))
            return round(val * 1000.0, 2)
    except ValueError:
        return None
    return None


def extract_weight_grams(text: str) -> Optional[float]:
    """
    Parses declared weight string and converts to float in grams.
    Supports both thousand-separated grams (e.g., "Khối lượng tối đa: 2,667g" -> 2667.0)
    and decimal kilograms/grams (e.g., "450g" -> 450.0, "1.2 kg" -> 1200.0).
    """
    if not text:
        return None

    # 1. Prioritize explicit weight label ("Khối lượng tối đa: 2,667g", "Trọng lượng: 0.75kg")
    match = WEIGHT_LABEL_PATTERN.search(text)
    if match:
        res = _parse_number_and_unit_to_grams(match.group(1), match.group(2))
        if res is not None:
            return res

    # 2. Fallback to any standalone weight pattern (excluding currency like 300.000đ)
    for m in WEIGHT_FALLBACK_PATTERN.finditer(text):
        res = _parse_number_and_unit_to_grams(m.group(1), m.group(2))
        if res is not None:
            return res

    return None


def extract_weight_text(text: str) -> Optional[str]:
    """
    Extracts raw weight string as presented on label (e.g., '2,667g') if available.
    """
    if not text:
        return None
    match = WEIGHT_LABEL_PATTERN.search(text)
    if match:
        return f"{match.group(1)}{match.group(2)}"
    match_fb = WEIGHT_FALLBACK_PATTERN.search(text)
    if match_fb:
        return f"{match_fb.group(1)}{match_fb.group(2)}"
    return None


def parse_shopee_screenshot_lines(lines: List[str]) -> Dict[str, Any]:
    """
    Parses OCR text lines from a Shopee order screenshot to extract:
    - tracking_number (sau phần 'Thông tin vận chuyển' -> 'SPX Express: SPXVN06152353863A')
    - recipient_name (sau phần 'Địa chỉ nhận hàng' -> 'Trần Hữu Quốc')
    - recipient_phone ('(+84) 911 547 697')
    """
    tracking_number: Optional[str] = None
    recipient_name: Optional[str] = None
    recipient_phone: Optional[str] = None

    # 1. Extract Tracking Number after "Thông tin vận chuyển" or "SPX Express:"
    in_shipping_section = False
    for line in lines:
        norm = _strip_accents(line)
        if "thong tin van chuyen" in norm or "thong tin vn chuyn" in norm:
            in_shipping_section = True
            continue

        if in_shipping_section:
            if ":" in line:
                after_colon = line.split(":", 1)[1].strip()
                cand = extract_tracking_number(after_colon) or after_colon.split()[0]
                if cand and len(cand) >= 8:
                    tracking_number = cand.upper()
                    break
            cand = extract_tracking_number(line)
            if cand:
                tracking_number = cand
                break

    # Fallback across all lines if not found in section
    if not tracking_number:
        full_text = "\n".join(lines)
        tracking_number = extract_tracking_number(full_text)

    # 2. Extract Recipient Name & Phone after "Địa chỉ nhận hàng"
    addr_idx = -1
    for idx, line in enumerate(lines):
        norm = _strip_accents(line)
        if ("dia chi" in norm or "da ch" in norm) and ("nhan hang" in norm or "nhn hang" in norm):
            addr_idx = idx
            break

    search_lines = lines[addr_idx + 1 : addr_idx + 5] if addr_idx != -1 else lines
    for line in search_lines:
        phone_match = PHONE_PATTERN.search(line)
        if phone_match:
            recipient_phone = re.sub(r"\s+", " ", phone_match.group(1)).strip()
            name_part = line[: phone_match.start()].strip()
            if name_part:
                recipient_name = _normalize_vietnamese_name(name_part)
            break

    # If name and phone were on separate consecutive lines after "Địa chỉ nhận hàng"
    if addr_idx != -1 and not recipient_name and len(lines) > addr_idx + 1:
        first_line = lines[addr_idx + 1]
        if not PHONE_PATTERN.search(first_line):
            recipient_name = _normalize_vietnamese_name(first_line)

    return {
        "tracking_number": tracking_number,
        "recipient_name": recipient_name,
        "recipient_phone": recipient_phone,
    }


def extract_shopee_screenshot(image_input: Union[str, bytes, np.ndarray]) -> Dict[str, Any]:
    """
    High-level function to process a Shopee order screenshot with PaddleOCR
    and return the 3 required fields in JSON-ready dictionary format.
    """
    lines = run_ocr_lines(image_input)
    return parse_shopee_screenshot_lines(lines)
