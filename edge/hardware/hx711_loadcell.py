"""
HX711 Load Cell Driver Module [Person 2].
Measures weight, filters sensor noise, and calculates weight deltas (ΔW)
for anti-theft and parcel verification.
"""
import math
import time
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from contracts.schemas import WeightMeasurement
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

# Default filtering & stability parameters
DEFAULT_SAMPLE_COUNT: int = 15
TRIM_RATIO: float = 0.2  # Discard 20% lowest and 20% highest readings (trimmed mean)
STABILITY_STD_DEV_GRAMS: float = 5.0  # Max standard deviation (grams) to consider reading stable


class LoadCellController:
    """Manages load cell sensors across locker compartments with noise filtering."""

    def __init__(
        self,
        mock_mode: bool = MOCK_HARDWARE,
        calibration_factor: float = LOADCELL_CALIBRATION_FACTOR,
    ):
        self.mock_mode = mock_mode or not RPI_AVAILABLE
        self.calibration_factor = calibration_factor if calibration_factor != 0 else 420.0
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
        GPIO.output(HX711_SCK_PIN, False)
        logger.info("HX711 pins initialized: DT=%d, SCK=%d", HX711_DT_PIN, HX711_SCK_PIN)

    @staticmethod
    def filter_samples(
        samples: List[float],
        trim_ratio: float = TRIM_RATIO,
    ) -> Tuple[float, float]:
        """
        Applies a Trimmed Mean / Median filter to reject HX711 ADC spikes and noise.

        Args:
            samples: Raw or converted weight readings.
            trim_ratio: Proportion of extreme low and high samples to discard (0.0 to 0.45).

        Returns:
            Tuple of (filtered_mean, standard_deviation).
        """
        valid = [float(s) for s in samples if s is not None]
        if not valid:
            return 0.0, 0.0
        if len(valid) == 1:
            return valid[0], 0.0

        sorted_samples = sorted(valid)
        n = len(sorted_samples)
        trim_count = int(n * max(0.0, min(trim_ratio, 0.45)))

        if trim_count > 0 and (n - 2 * trim_count) >= 1:
            trimmed = sorted_samples[trim_count : n - trim_count]
        else:
            trimmed = sorted_samples

        mean_val = sum(trimmed) / len(trimmed)
        if len(trimmed) > 1:
            variance = sum((x - mean_val) ** 2 for x in trimmed) / len(trimmed)
            std_dev = math.sqrt(variance)
        else:
            std_dev = 0.0

        return mean_val, std_dev

    def _read_raw_hx711(self) -> Optional[float]:
        """Bit-bangs a single 24-bit ADC sample from HX711."""
        if self.mock_mode:
            return 0.0

        # Wait for DT to go LOW (HX711 ready)
        timeout = time.time() + 1.0
        while GPIO.input(HX711_DT_PIN) == 1:
            if time.time() > timeout:
                logger.warning("HX711 timeout waiting for ready signal.")
                return None
            time.sleep(0.001)

        count = 0
        for _ in range(24):
            GPIO.output(HX711_SCK_PIN, True)
            count = count << 1
            GPIO.output(HX711_SCK_PIN, False)
            if GPIO.input(HX711_DT_PIN):
                count += 1

        # 25th pulse sets Channel A, Gain 128 for next reading
        GPIO.output(HX711_SCK_PIN, True)
        GPIO.output(HX711_SCK_PIN, False)

        # 24-bit 2's complement conversion
        if count & 0x800000:
            count -= 0x1000000

        return float(count)

    def _read_filtered_hx711(
        self,
        samples: int = DEFAULT_SAMPLE_COUNT,
        sample_delay_sec: float = 0.01,
    ) -> Tuple[float, float]:
        """
        Reads multiple raw samples from HX711 and applies outlier filtering.

        Returns:
            Tuple of (filtered_raw_value, raw_std_dev).
        """
        raw_samples: List[float] = []
        for _ in range(max(1, samples)):
            val = self._read_raw_hx711()
            if val is not None:
                raw_samples.append(val)
            if sample_delay_sec > 0:
                time.sleep(sample_delay_sec)

        if not raw_samples:
            logger.error("No valid samples read from HX711.")
            return 0.0, float("inf")

        return self.filter_samples(raw_samples)

    def tare(self, locker_id: int = 1, samples: int = DEFAULT_SAMPLE_COUNT):
        """Zeroes the load cell before parcel is placed using filtered multi-sample average."""
        if self.mock_mode:
            logger.info("[Mock HX711] Taring locker %d to 0.0g", locker_id)
            self.tare_offsets[locker_id] = 0.0
            self.last_readings[locker_id] = 0.0
            return

        logger.info("Taring locker %d with %d samples...", locker_id, samples)
        filtered_raw, _ = self._read_filtered_hx711(samples=samples)
        self.tare_offsets[locker_id] = filtered_raw
        self.last_readings[locker_id] = 0.0
        logger.info("Locker %d tare offset set to %.2f", locker_id, filtered_raw)

    def measure_weight_delta(
        self,
        locker_id: int = 1,
        expected_weight: Optional[float] = None,
        samples: int = DEFAULT_SAMPLE_COUNT,
    ) -> WeightMeasurement:
        """
        Samples readings, filters noise, checks stability, and returns weight delta (ΔW).
        If in mock mode, returns realistic mock measurement close to expected_weight.
        """
        previous_weight = self.last_readings.get(locker_id, 0.0)

        if self.mock_mode:
            time.sleep(0.2)
            target = expected_weight if expected_weight is not None else 450.0
            simulated_weight = round(target + 5.0, 2)
            delta_g = round(simulated_weight - previous_weight, 2)
            self.last_readings[locker_id] = simulated_weight
            logger.info(
                "[Mock HX711] Locker %d weight: %.2f g (ΔW: %.2f g)",
                locker_id,
                simulated_weight,
                delta_g,
            )
            return WeightMeasurement(
                locker_id=locker_id,
                current_weight_grams=simulated_weight,
                delta_grams=delta_g,
                is_stable=True,
                timestamp=datetime.now(timezone.utc),
            )

        # Allow parcel to settle on physical tray before sampling
        time.sleep(WEIGH_STABILIZATION_TIME_SEC)

        filtered_raw, raw_std_dev = self._read_filtered_hx711(samples=samples)
        tare_offset = self.tare_offsets.get(locker_id, 0.0)

        weight_g = max(0.0, (filtered_raw - tare_offset) / self.calibration_factor)
        std_dev_grams = abs(raw_std_dev / self.calibration_factor)
        is_stable = std_dev_grams <= STABILITY_STD_DEV_GRAMS

        delta_g = weight_g - previous_weight
        self.last_readings[locker_id] = weight_g

        logger.info(
            "Locker %d measured: %.2f g (ΔW: %.2f g, std: %.2f g, stable: %s)",
            locker_id,
            weight_g,
            delta_g,
            std_dev_grams,
            is_stable,
        )

        return WeightMeasurement(
            locker_id=locker_id,
            current_weight_grams=round(weight_g, 2),
            delta_grams=round(delta_g, 2),
            is_stable=is_stable,
            timestamp=datetime.now(timezone.utc),
        )


# Module-level singleton & helper function for direct Contract import
_default_loadcell_controller: Optional[LoadCellController] = None


def get_loadcell_controller() -> LoadCellController:
    """Returns or initializes the default LoadCellController singleton."""
    global _default_loadcell_controller
    if _default_loadcell_controller is None:
        _default_loadcell_controller = LoadCellController()
    return _default_loadcell_controller


def measure_weight_delta(
    locker_id: int = 1,
    expected_weight: Optional[float] = None,
) -> WeightMeasurement:
    """Contract convenience function returning WeightMeasurement for Person 3."""
    return get_loadcell_controller().measure_weight_delta(
        locker_id=locker_id,
        expected_weight=expected_weight,
    )

