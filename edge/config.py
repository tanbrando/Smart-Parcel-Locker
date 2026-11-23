"""
Hardware Pinout and System Configurations for Raspberry Pi 4B Edge Device.
"""
import os
from typing import Dict, List

# Load .env configuration if present
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
except ImportError:
    pass

# Server Network Configuration
SERVER_API_URL: str = os.getenv("SERVER_API_URL", "http://localhost:8000")
API_TIMEOUT_SECONDS: float = float(os.getenv("API_TIMEOUT_SECONDS", "15.0"))

# Hardware Mock Mode Switch
# Automatically true if not running on Raspberry Pi or if env var is set
try:
    import RPi.GPIO as GPIO  # noqa: F401
    DEFAULT_MOCK = False
except (ImportError, RuntimeError):
    DEFAULT_MOCK = True

MOCK_HARDWARE: bool = os.getenv("MOCK_HARDWARE", str(DEFAULT_MOCK)).lower() in ("true", "1", "yes")

# Camera Configuration
CAMERA_INDEX: int = int(os.getenv("CAMERA_INDEX", "0"))
CAMERA_FRAME_WIDTH: int = 1280
CAMERA_FRAME_HEIGHT: int = 720
SCAN_TIMEOUT_SECONDS: float = 12.0

# Camera Mode: "test" (uses static image from test folder) or "raspberry" / "live" (uses CSI / USB Camera on Pi)
DEFAULT_CAMERA_MODE: str = "test" if MOCK_HARDWARE else "raspberry"
CAMERA_MODE: str = os.getenv("CAMERA_MODE", DEFAULT_CAMERA_MODE).lower()
USE_CSI_CAMERA: bool = os.getenv("USE_CSI_CAMERA", "true").lower() in ("true", "1", "yes")
CAMERA_PREVIEW: bool = os.getenv("CAMERA_PREVIEW", "false").lower() in ("true", "1", "yes")

# Default test image paths
EDGE_DIR: str = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR: str = os.getenv("PADDLE_PDX_CACHE_HOME", os.path.join(EDGE_DIR, "models", "paddlex"))
os.environ["PADDLE_PDX_CACHE_HOME"] = MODELS_DIR

DEFAULT_TEST_CAMERA_IMAGE: str = os.getenv(
    "TEST_CAMERA_IMAGE",
    os.path.join(EDGE_DIR, "test", "cameras", "shopee.jpg"),
)
DEFAULT_TEST_SCREENSHOT_IMAGE: str = os.getenv(
    "TEST_SCREENSHOT_IMAGE",
    os.path.join(EDGE_DIR, "test", "screenshots", "shopee.jpg"),
)

# GPIO Pinout Mapping (BCM Numbers)
# Servo Motors (PWM control for door locking/opening mechanism, e.g., SG90 / MG996R)
LOCKER_SERVO_PINS: Dict[int, int] = {
    1: 17,  # Locker 1 Servo Signal Pin
    2: 27,  # Locker 2 Servo Signal Pin
    3: 22,  # Locker 3 Servo Signal Pin
    4: 4,   # Locker 4 Servo Signal Pin
}
# Backward compatibility alias
LOCKER_RELAY_PINS = LOCKER_SERVO_PINS

# Servo angles & timing
SERVO_PWM_FREQUENCY: int = 50           # Standard 50Hz for RC servos (20ms period)
SERVO_LOCKED_ANGLE: float = 0.0         # Angle when door is locked (0 degrees)
SERVO_UNLOCKED_ANGLE: float = 90.0      # Angle when door is open (90 degrees)
DOOR_UNLOCK_DURATION_SEC: float = 4.0   # Duration to keep unlocked before returning to locked

# Partial-hardware testing switches (useful before wiring all 4 compartments / sensors)
# ACTIVE_LOCKER_IDS controls which locker servos are initialized on GPIO (default: 1,2,3,4)
_raw_active_lockers = os.getenv("ACTIVE_LOCKER_IDS", "1,2,3,4")
ACTIVE_LOCKER_IDS: List[int] = [
    int(tok.strip()) for tok in _raw_active_lockers.split(",") if tok.strip().isdigit()
] or [1, 2, 3, 4]

# Set ENABLE_ULTRASONIC=false to simulate parcel presence (14cm) when HC-SR04 is not wired yet.
ENABLE_ULTRASONIC: bool = os.getenv("ENABLE_ULTRASONIC", "true").lower() in ("true", "1", "yes")

# Door Reed Switch / Limit Switch Sensor (Door closed detection)
# Active LOW: Grounded when magnet contacts switch (door closed)
# Set ENABLE_DOOR_SWITCH=false if your physical enclosure does not have magnetic reed switches wired yet.
ENABLE_DOOR_SWITCH: bool = os.getenv("ENABLE_DOOR_SWITCH", "true").lower() in ("true", "1", "yes")
DOOR_SWITCH_PINS: Dict[int, int] = {
    1: 7,   # Locker 1 Reed Switch
    2: 8,   # Locker 2 Reed Switch
    3: 9,   # Locker 3 Reed Switch
    4: 11,  # Locker 4 Reed Switch
}
DOOR_SWITCH_CLOSED_ACTIVE_LOW: bool = True

# Ultrasonic Distance Sensor (HC-SR04 / JSN-SR04T)
# Shared TRIG (GPIO 5) across all 4 compartments (measured sequentially), dedicated ECHO per locker.
# CAUTION: 5V output from HC-SR04 ECHO must use a 1k/2k voltage divider before Pi 3.3V GPIO!
ULTRASONIC_TRIG_PINS: Dict[int, int] = {
    1: 5,   # Shared Ultrasonic TRIG
    2: 5,   # Shared Ultrasonic TRIG
    3: 5,   # Shared Ultrasonic TRIG
    4: 5,   # Shared Ultrasonic TRIG
}
ULTRASONIC_ECHO_PINS: Dict[int, int] = {
    1: 6,   # Locker 1 Ultrasonic ECHO
    2: 13,  # Locker 2 Ultrasonic ECHO
    3: 19,  # Locker 3 Ultrasonic ECHO
    4: 26,  # Locker 4 Ultrasonic ECHO
}

# Ultrasonic calibration and threshold (cm)
BASELINE_EMPTY_CM: float = float(os.getenv("BASELINE_EMPTY_CM", "35.0"))  # Empty locker height
OCCUPIED_MARGIN_CM: float = float(os.getenv("OCCUPIED_MARGIN_CM", "5.0"))  # Margin to trigger occupied
MIN_FREE_DISTANCE_CM: float = float(os.getenv("MIN_FREE_DISTANCE_CM", "8.0"))  # Min clearance to allow batching
ULTRASONIC_TIMEOUT_SEC: float = 0.03  # Max echo timeout (~5 meters roundtrip)
ULTRASONIC_SAMPLE_COUNT: int = 5      # Number of samples for median filter
ULTRASONIC_DEBOUNCE_COUNT: int = 3    # Consecutive stable readings required for decision

# 4x4 Matrix Keypad Pinout (Conflict-free with Servos, HC-SR04, Door Switches, Buzzer & I2C)
KEYPAD_ROW_PINS: List[int] = [18, 23, 24, 25]  # R1, R2, R3, R4
KEYPAD_COL_PINS: List[int] = [12, 16, 20, 21]  # C1, C2, C3, C4
KEYPAD_MAX_ATTEMPTS: int = 3
KEYPAD_LOCKOUT_SECONDS: int = 60

# Indicators: LCD 1602 (I2C on GPIO 2/3) & Buzzer
LCD_I2C_ADDR: int = 0x27
LCD_I2C_BUS: int = 1
LCD_COLS: int = 16
LCD_ROWS: int = 2

BUZZER_PIN: int = 10
BUZZER_ACTIVE_HIGH: bool = True


def validate_gpio_pinout() -> List[str]:
    """
    Validates that no BCM GPIO pins conflict across peripherals on Raspberry Pi 4B.
    Shared TRIG across ultrasonic sensors is explicitly allowed.
    Returns a list of conflict descriptions (empty list means valid).
    """
    pin_owners: Dict[int, str] = {
        2: "I2C_SDA",
        3: "I2C_SCL",
    }
    conflicts: List[str] = []

    def _claim(pin: int, owner: str):
        if pin in pin_owners:
            conflicts.append(f"GPIO {pin} conflict: {pin_owners[pin]} vs {owner}")
        else:
            pin_owners[pin] = owner

    for locker_id, pin in LOCKER_SERVO_PINS.items():
        _claim(pin, f"SERVO_{locker_id}")
    for pin in set(ULTRASONIC_TRIG_PINS.values()):
        _claim(pin, "ULTRASONIC_TRIG")
    for locker_id, pin in ULTRASONIC_ECHO_PINS.items():
        _claim(pin, f"ULTRASONIC_ECHO_{locker_id}")
    for locker_id, pin in DOOR_SWITCH_PINS.items():
        _claim(pin, f"DOOR_SWITCH_{locker_id}")
    for idx, pin in enumerate(KEYPAD_ROW_PINS, 1):
        _claim(pin, f"KEYPAD_ROW_{idx}")
    for idx, pin in enumerate(KEYPAD_COL_PINS, 1):
        _claim(pin, f"KEYPAD_COL_{idx}")
    _claim(BUZZER_PIN, "BUZZER")
    return conflicts
