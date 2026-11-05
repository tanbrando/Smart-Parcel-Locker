"""
HX711 Load Cell Driver Module [Person 2].
Measures weight and calculates weight deltas for anti-theft and parcel verification.
"""
import time
import logging
from datetime import datetime, timezone
from typing import Dict

from contracts.schemas import WeightMeasurement
from contracts.mock_data import MOCK_WEIGHT_MEASUREMENT_MATCH
from edge.config import (
    HX711_DT_PIN,
    HX711_SCK_PIN,
    LOADCELL_CALIBRATION_FACTOR,
    MOCK_HARDWARE,
    WEIGH_STABILIZATION_TIME_SEC,
)

logger = logging.getLogger("edge.hardware.hx711")

try:
    import RPi.GPIO as GPIO
    RPI_AVAILABLE = True
except (ImportError, RuntimeError):
    RPI_AVAILABLE = False


class LoadCellController:
    """Manages load cell sensors across locker compartments."""

    def __init__(self, mock_mode: bool = MOCK_HARDWARE):
        self.mock_mode = mock_mode or not RPI_AVAILABLE
        self.tare_offsets: Dict[int, float] = {1: 0.0, 2: 0.0, 3: 0.0}
        self.last_readings: Dict[int, float] = {1: 0.0, 2: 0.0, 3: 0.0}

        if self.mock_mode:
            logger.info("LoadCellController initialized in MOCK mode.")
        else:
            self._setup_hardware()

    def _setup_hardware(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(HX711_SCK_PIN, GPIO.OUT)
        GPIO.setup(HX711_DT_PIN, GPIO.IN)
        logger.info("HX711 pins initialized: DT=%d, SCK=%d", HX711_DT_PIN, HX711_SCK_PIN)

    def tare(self, locker_id: int = 1):
        """Zeroes the load cell before parcel is placed."""
        if self.mock_mode:
            logger.info("[Mock HX711] Taring locker %d to 0.0g", locker_id)
            self.tare_offsets[locker_id] = 0.0
            self.last_readings[locker_id] = 0.0
            return

        # Real hardware tare: sample readings and store average offset
        logger.info("Taring locker %d...", locker_id)
        raw_val = self._read_raw_hx711()
        self.tare_offsets[locker_id] = raw_val

    def _read_raw_hx711(self) -> float:
        """Bit-bangs HX711 24-bit ADC output."""
        if self.mock_mode:
            return 0.0

        # Wait for DT to go LOW (ready)
        timeout = time.time() + 1.0
        while GPIO.input(HX711_DT_PIN) == 1:
            if time.time() > timeout:
                logger.warning("HX711 timeout waiting for ready.")
                return 0.0
            time.sleep(0.001)

        count = 0
        for _ in range(24):
            GPIO.output(HX711_SCK_PIN, True)
            count = count << 1
            GPIO.output(HX711_SCK_PIN, False)
            if GPIO.input(HX711_DT_PIN):
                count += 1

        # 25th pulse sets gain to 128
        GPIO.output(HX711_SCK_PIN, True)
        GPIO.output(HX711_SCK_PIN, False)

        # 2's complement conversion
        if count & 0x800000:
            count -= 0x1000000

        return float(count)

    def measure_weight_delta(self, locker_id: int = 1, expected_weight: float = None) -> WeightMeasurement:
        """
        Samples readings, waits for stabilization, and returns weight delta.
        If in mock mode, returns realistic mock measurement close to expected_weight.
        """
        if self.mock_mode:
            time.sleep(1.0)
            target = expected_weight if expected_weight is not None else 450.0
            simulated_weight = round(target + 5.0, 1)
            logger.info("[Mock HX711] Measured locker %d weight: %s g", locker_id, simulated_weight)
            return WeightMeasurement(
                locker_id=locker_id,
                current_weight_grams=simulated_weight,
                delta_grams=simulated_weight,
                is_stable=True,
                timestamp=datetime.now(timezone.utc),
            )

        # Allow parcel to settle on physical tray
        time.sleep(WEIGH_STABILIZATION_TIME_SEC)
        raw_val = self._read_raw_hx711()
        weight_g = max(0.0, (raw_val - self.tare_offsets.get(locker_id, 0.0)) / LOADCELL_CALIBRATION_FACTOR)
        delta = weight_g - self.last_readings.get(locker_id, 0.0)
        self.last_readings[locker_id] = weight_g

        return WeightMeasurement(
            locker_id=locker_id,
            current_weight_grams=round(weight_g, 2),
            delta_grams=round(delta, 2),
            is_stable=True,
            timestamp=datetime.now(timezone.utc),
        )
