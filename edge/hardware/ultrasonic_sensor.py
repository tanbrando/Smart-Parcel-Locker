"""
Ultrasonic Occupancy Sensor Driver Module [Person 2].
Measures distance inside locker using HC-SR04 / JSN-SR04T to detect if a parcel is present.
Features Median Filtering, Outlier Rejection, Baseline Calibration, Debounce, and Full Mocking.
"""
import time
import logging
from typing import Dict, List, Optional
from datetime import datetime, timezone

from contracts.schemas import OccupancyResult
from edge.config import (
    BASELINE_EMPTY_CM,
    OCCUPIED_MARGIN_CM,
    ENABLE_ULTRASONIC,
    ULTRASONIC_TRIG_PINS,
    ULTRASONIC_ECHO_PINS,
    ULTRASONIC_TIMEOUT_SEC,
    ULTRASONIC_SAMPLE_COUNT,
    ULTRASONIC_DEBOUNCE_COUNT,
    MOCK_HARDWARE,
)

logger = logging.getLogger("edge.hardware.ultrasonic")

try:
    import RPi.GPIO as GPIO
    RPI_AVAILABLE = True
except (ImportError, RuntimeError):
    RPI_AVAILABLE = False


class UltrasonicSensor:
    """Controls ultrasonic distance sensor(s) for parcel occupancy detection."""

    def __init__(
        self,
        mock_mode: bool = MOCK_HARDWARE,
        baseline_empty_cm: float = BASELINE_EMPTY_CM,
        occupied_margin_cm: float = OCCUPIED_MARGIN_CM,
        enabled: bool = ENABLE_ULTRASONIC,
    ):
        self.enabled = enabled
        self.mock_mode = mock_mode or not RPI_AVAILABLE or not self.enabled
        self.baseline_empty_cm = baseline_empty_cm
        self.occupied_margin_cm = occupied_margin_cm
        self.trig_pins: Dict[int, int] = dict(ULTRASONIC_TRIG_PINS)
        self.echo_pins: Dict[int, int] = dict(ULTRASONIC_ECHO_PINS)
        self.baselines_cm: Dict[int, float] = {k: baseline_empty_cm for k in self.trig_pins}

        # When ENABLE_ULTRASONIC=false (partial hardware test), simulate parcel detected (14cm)
        default_mock_dist = 14.0 if not self.enabled else baseline_empty_cm
        self._mock_distance_cm: Dict[int, Optional[float]] = {k: default_mock_dist for k in self.trig_pins}
        self._mock_error: Optional[str] = None

        if self.mock_mode:
            if not self.enabled:
                logger.info("UltrasonicSensor disabled (ENABLE_ULTRASONIC=false): simulating occupied at 14.0 cm.")
            else:
                logger.info("UltrasonicSensor initialized in MOCK mode.")
        else:
            self._setup_hardware()

    def _setup_hardware(self):
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        configured_trigs = set()
        for locker_id in self.trig_pins:
            t_pin = self.trig_pins[locker_id]
            e_pin = self.echo_pins[locker_id]
            if t_pin not in configured_trigs:
                GPIO.setup(t_pin, GPIO.OUT)
                GPIO.output(t_pin, False)
                configured_trigs.add(t_pin)
            GPIO.setup(e_pin, GPIO.IN)
            logger.info("Locker %d Ultrasonic pins: TRIG=%d, ECHO=%d", locker_id, t_pin, e_pin)
        time.sleep(0.05)  # Let sensor settle

    def set_mock_distance(self, distance_cm: Optional[float], locker_id: int = 1, error: Optional[str] = None):
        """Allows test fixtures to simulate parcel placement or sensor timeout."""
        self._mock_distance_cm[locker_id] = distance_cm
        self._mock_error = error

    def _read_raw_pulse_cm(self, locker_id: int = 1) -> Optional[float]:
        """Sends a 10us TRIG pulse and measures duration of ECHO signal."""
        if self.mock_mode:
            if self._mock_error:
                return None
            return self._mock_distance_cm.get(locker_id, self.baseline_empty_cm)

        if locker_id not in self.trig_pins or locker_id not in self.echo_pins:
            logger.error("Invalid locker_id for ultrasonic: %d", locker_id)
            return None

        t_pin = self.trig_pins[locker_id]
        e_pin = self.echo_pins[locker_id]

        # 1. Trigger pulse
        GPIO.output(t_pin, True)
        time.sleep(0.00001)  # 10 microseconds
        GPIO.output(t_pin, False)

        pulse_start = time.perf_counter()
        timeout_start = pulse_start + ULTRASONIC_TIMEOUT_SEC

        # 2. Wait for ECHO to go HIGH
        while GPIO.input(e_pin) == 0:
            pulse_start = time.perf_counter()
            if pulse_start > timeout_start:
                logger.warning("Ultrasonic sensor timeout waiting for echo start on locker %d", locker_id)
                return None

        # 3. Wait for ECHO to go LOW
        pulse_end = pulse_start
        timeout_end = pulse_start + ULTRASONIC_TIMEOUT_SEC
        while GPIO.input(e_pin) == 1:
            pulse_end = time.perf_counter()
            if pulse_end > timeout_end:
                logger.warning("Ultrasonic sensor timeout waiting for echo end on locker %d", locker_id)
                return None

        pulse_duration = pulse_end - pulse_start
        # Speed of sound is approx 34300 cm/s -> distance = (duration * 34300) / 2 = duration * 17150
        distance_cm = pulse_duration * 17150.0

        # Reject out-of-range readings (HC-SR04 nominal range: 2cm to 400cm)
        if distance_cm < 2.0 or distance_cm > 400.0:
            return None

        return round(distance_cm, 2)

    def measure_distance_cm(
        self,
        locker_id: int = 1,
        samples: int = ULTRASONIC_SAMPLE_COUNT,
        sample_delay_sec: float = 0.02,
    ) -> Optional[float]:
        """
        Samples distance multiple times and applies a Median Filter to eliminate noise/spikes.
        Returns distance in cm, or None if sensor failed or timed out.
        """
        readings: List[float] = []
        for _ in range(max(1, samples)):
            d = self._read_raw_pulse_cm(locker_id)
            if d is not None:
                readings.append(d)
            if sample_delay_sec > 0:
                time.sleep(sample_delay_sec)

        if not readings:
            logger.warning("No valid ultrasonic readings obtained for locker %d", locker_id)
            return None

        # Median calculation
        readings.sort()
        mid = len(readings) // 2
        if len(readings) % 2 == 1:
            median_val = readings[mid]
        else:
            median_val = (readings[mid - 1] + readings[mid]) / 2.0

        return round(median_val, 2)

    def calibrate_empty_baseline(self, locker_id: int = 1, samples: int = 20) -> float:
        """
        Measures empty locker baseline distance (cm) for a specific locker compartment.
        """
        logger.info("Calibrating empty locker baseline for locker %d (%d samples)...", locker_id, samples)
        d = self.measure_distance_cm(locker_id, samples=samples, sample_delay_sec=0.03)
        if d is not None and d > 0:
            self.baselines_cm[locker_id] = d
            self.baseline_empty_cm = d
            logger.info("Calibrated baseline for locker %d: %.2f cm", locker_id, d)
            return d
        fallback = self.baselines_cm.get(locker_id, self.baseline_empty_cm)
        logger.warning("Calibration failed, keeping default baseline: %.2f cm", fallback)
        return fallback

    def is_locker_occupied(
        self,
        locker_id: int = 1,
        debounce_count: int = ULTRASONIC_DEBOUNCE_COUNT,
    ) -> OccupancyResult:
        """
        Determines whether the locker contains a parcel using debounced consecutive readings.
        Condition for occupied: distance < (baseline_cm - occupied_margin_cm).
        """
        baseline_cm = self.baselines_cm.get(locker_id, self.baseline_empty_cm)
        threshold_cm = baseline_cm - self.occupied_margin_cm
        consecutive_results: List[bool] = []
        last_distance: Optional[float] = None

        for _ in range(max(1, debounce_count)):
            dist = self.measure_distance_cm(locker_id, samples=ULTRASONIC_SAMPLE_COUNT)
            if dist is None:
                # Sensor error or timeout -> fail safe: report not occupied with error flag
                return OccupancyResult(
                    occupied=False,
                    distance_cm=None,
                    baseline_cm=baseline_cm,
                    confidence=0.0,
                    error="SENSOR_TIMEOUT",
                    timestamp=datetime.now(timezone.utc),
                )
            last_distance = dist
            is_occ = dist < threshold_cm
            consecutive_results.append(is_occ)
            time.sleep(0.01)

        # Confidence is ratio of matches to total readings
        occupied_votes = sum(1 for r in consecutive_results if r)
        total_votes = len(consecutive_results)
        final_occupied = occupied_votes >= (total_votes / 2.0)
        confidence = occupied_votes / total_votes if final_occupied else (total_votes - occupied_votes) / total_votes

        logger.info(
            "Locker %d occupancy check: occupied=%s, dist=%.2f cm, baseline=%.2f cm (threshold=%.2f cm, conf=%.2f)",
            locker_id,
            final_occupied,
            last_distance,
            baseline_cm,
            threshold_cm,
            confidence,
        )

        return OccupancyResult(
            occupied=final_occupied,
            distance_cm=last_distance,
            baseline_cm=baseline_cm,
            confidence=round(confidence, 2),
            error=None,
            timestamp=datetime.now(timezone.utc),
        )


# Singleton instance & Module-level convenience functions
_default_ultrasonic_sensor: Optional[UltrasonicSensor] = None


def get_ultrasonic_sensor() -> UltrasonicSensor:
    """Returns or initializes default UltrasonicSensor singleton."""
    global _default_ultrasonic_sensor
    if _default_ultrasonic_sensor is None:
        _default_ultrasonic_sensor = UltrasonicSensor()
    return _default_ultrasonic_sensor


def measure_distance_cm(locker_id: int = 1, samples: int = ULTRASONIC_SAMPLE_COUNT) -> Optional[float]:
    """Measures distance in cm (median filtered) for locker_id."""
    return get_ultrasonic_sensor().measure_distance_cm(locker_id=locker_id, samples=samples)


def calibrate_empty_baseline(locker_id: int = 1, samples: int = 20) -> float:
    """Calibrates empty locker baseline for locker_id."""
    return get_ultrasonic_sensor().calibrate_empty_baseline(locker_id=locker_id, samples=samples)


def is_locker_occupied(locker_id: int = 1) -> OccupancyResult:
    """Checks whether parcel is present inside locker_id."""
    return get_ultrasonic_sensor().is_locker_occupied(locker_id=locker_id)
