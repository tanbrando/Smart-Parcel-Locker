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

# Door Reed Switch / Limit Switch Sensor (Door closed detection)
# Active LOW: Grounded when magnet contacts switch (door closed)
DOOR_SWITCH_PINS: Dict[int, int] = {
    1: 23,  # Locker 1 Reed Switch
    2: 24,  # Locker 2 Reed Switch
    3: 25,  # Locker 3 Reed Switch
    4: 7,   # Locker 4 Reed Switch
}
DOOR_SWITCH_CLOSED_ACTIVE_LOW: bool = True

# Ultrasonic Distance Sensor (HC-SR04 / JSN-SR04T)
# TRIG: Output 10us trigger pulse
# ECHO: Input pulse width (CAUTION: 5V output from HC-SR04 must use voltage divider before Pi GPIO!)
ULTRASONIC_TRIG_PINS: Dict[int, int] = {
    1: 5,   # Locker 1 Ultrasonic TRIG
    2: 19,  # Locker 2 Ultrasonic TRIG
    3: 13,  # Locker 3 Ultrasonic TRIG
    4: 8,   # Locker 4 Ultrasonic TRIG
}
ULTRASONIC_ECHO_PINS: Dict[int, int] = {
    1: 6,   # Locker 1 Ultrasonic ECHO
    2: 20,  # Locker 2 Ultrasonic ECHO
    3: 16,  # Locker 3 Ultrasonic ECHO
    4: 9,   # Locker 4 Ultrasonic ECHO
}

# Ultrasonic calibration and threshold (cm)
BASELINE_EMPTY_CM: float = float(os.getenv("BASELINE_EMPTY_CM", "35.0"))  # Empty locker height
OCCUPIED_MARGIN_CM: float = float(os.getenv("OCCUPIED_MARGIN_CM", "5.0"))  # Margin to trigger occupied
ULTRASONIC_TIMEOUT_SEC: float = 0.03  # Max echo timeout (~5 meters roundtrip)
ULTRASONIC_SAMPLE_COUNT: int = 5      # Number of samples for median filter
ULTRASONIC_DEBOUNCE_COUNT: int = 3    # Consecutive stable readings required for decision

# 4x4 Matrix Keypad Pinout
KEYPAD_ROW_PINS: List[int] = [18, 23, 24, 25]  # R1, R2, R3, R4
KEYPAD_COL_PINS: List[int] = [12, 16, 20, 21]  # C1, C2, C3, C4
KEYPAD_MAX_ATTEMPTS: int = 3
KEYPAD_LOCKOUT_SECONDS: int = 60

# Indicators: LCD 1602 (I2C) & Buzzer
LCD_I2C_ADDR: int = 0x27
LCD_I2C_BUS: int = 1
LCD_COLS: int = 16
LCD_ROWS: int = 2

BUZZER_PIN: int = 26
BUZZER_ACTIVE_HIGH: bool = True
