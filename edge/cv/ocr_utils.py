"""
OCR and Text Parsing Utilities [Person 1].
Extracts tracking numbers and declared parcel weights from waybill labels.
"""
import re
from typing import Optional

# Common Vietnamese and Regional Courier Tracking Regexes
TRACKING_PATTERNS = [
    # Shopee Express (SPX): e.g., SPX038472918VN, SPXVN02837192
    r"\b(SPX[A-Z0-9]{8,14}(?:VN)?)\b",
    # Giao Hang Nhanh (GHN): e.g., GHN78921820, G8X129Y7
    r"\b(GHN[A-Z0-9]{6,12})\b",
    # Giao Hang Tiet Kiem (GHTK): e.g., S22184918.BO.128, 1204891283
    r"\b(S\d{6,10}\.[A-Z0-9\.]+)\b",
    # Viettel Post: e.g., VT892182012, 1892019281
    r"\b(VT[0-9]{8,12})\b",
    # J&T Express: e.g., 841209384712, 5521948192
    r"\b(84\d{10,12})\b",
    # Fallback generic tracking alphanumeric code (8-16 chars)
    r"\b([A-Z]{2,4}\d{8,12}[A-Z]{0,2})\b",
]

# Weight Regex: matches "450g", "0.5 kg", "1.2kg", "Khoi luong: 500 gr"
WEIGHT_PATTERN = re.compile(
    r"(?:trọng\s*lượng|khối\s*lượng|weight|kl|gw|nw)?\s*[:=\-]?\s*(\d+(?:[\.,]\d+)?)\s*(kg|kilo|kilogram|g|gr|gram)\b",
    re.IGNORECASE,
)


def extract_tracking_number(text: str) -> Optional[str]:
    """
    Scans raw text to match courier tracking number patterns.
    Returns normalized uppercase tracking string or None.
    """
    if not text:
        return None

    cleaned = text.strip()
    for pattern in TRACKING_PATTERNS:
        match = re.search(pattern, cleaned, re.IGNORECASE)
        if match:
            return match.group(1).upper()

    return None


def extract_weight_grams(text: str) -> Optional[float]:
    """
    Parses declared weight string and converts to float in grams.
    Returns grams (float) or None if not found.
    """
    if not text:
        return None

    match = WEIGHT_PATTERN.search(text)
    if not match:
        return None

    val_str = match.group(1).replace(",", ".")
    unit_str = match.group(2).lower()

    try:
        val = float(val_str)
        if unit_str in ("kg", "kilo", "kilogram"):
            return round(val * 1000.0, 2)
        elif unit_str in ("g", "gr", "gram"):
            return round(val, 2)
    except ValueError:
        return None

    return None

