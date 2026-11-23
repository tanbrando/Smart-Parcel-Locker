#!/usr/bin/env python3
"""
Interactive Hardware Test & Calibration Script for 4x HC-SR04 Ultrasonic Sensors.

Usage on Raspberry Pi:
  python scripts/test_ultrasonic.py                    # Live monitor all 4 lockers (#1..#4)
  python scripts/test_ultrasonic.py --lockers 1,2      # Monitor only lockers 1 & 2
  python scripts/test_ultrasonic.py --once             # Single reading pass then exit
  python scripts/test_ultrasonic.py --calibrate        # Measure empty baseline (20 samples/locker)
  python scripts/test_ultrasonic.py --mock --once      # Dry-run on PC without Raspberry Pi
"""
import argparse
import sys
import time
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from edge.config import (
    BASELINE_EMPTY_CM,
    MOCK_HARDWARE,
    OCCUPIED_MARGIN_CM,
    ULTRASONIC_ECHO_PINS,
    ULTRASONIC_TRIG_PINS,
)
from edge.hardware.ultrasonic_sensor import UltrasonicSensor

ECHO_PHYSICAL_PINS = {1: 31, 2: 33, 3: 35, 4: 37}


def _parse_locker_ids(raw: str) -> List[int]:
    ids = []
    for tok in raw.split(","):
        tok = tok.strip()
        if tok.isdigit():
            lid = int(tok)
            if lid in ULTRASONIC_ECHO_PINS and lid not in ids:
                ids.append(lid)
    return ids or [1, 2, 3, 4]


def _fill_bar(distance_cm: float, baseline_cm: float, width: int = 10) -> tuple[str, int]:
    if baseline_cm <= 0:
        return "." * width, 0
    pct = max(0, min(100, int(round(((baseline_cm - distance_cm) / baseline_cm) * 100))))
    filled = int(round((pct / 100.0) * width))
    return "#" * filled + "-" * (width - filled), pct


def run_calibration(sensor: UltrasonicSensor, locker_ids: List[int]):
    print("==================================================================")
    print("📏 HIỆU CHUẨN CHIỀU CAO TỦ RỖNG (BASELINE) CHO 4 CẢM BIẾN HC-SR04")
    print("   👉 Đảm bảo các ngăn tủ đang TRỐNG hoàn toàn trước khi đo...")
    print("==================================================================")
    measured = []
    for lid in locker_ids:
        t_pin = ULTRASONIC_TRIG_PINS[lid]
        e_pin = ULTRASONIC_ECHO_PINS[lid]
        d = sensor.calibrate_empty_baseline(locker_id=lid, samples=20)
        raw = sensor.measure_distance_cm(locker_id=lid, samples=5)
        if raw is None:
            print(f"  Ngăn #{lid} (TRIG={t_pin}, ECHO={e_pin}/Pin {ECHO_PHYSICAL_PINS[lid]}): ❌ TIMEOUT (kiểm tra dây/nguồn/chia áp)")
        else:
            measured.append(d)
            print(f"  Ngăn #{lid} (TRIG={t_pin}, ECHO={e_pin}/Pin {ECHO_PHYSICAL_PINS[lid]}): ✅ Baseline = {d:.2f} cm")
        time.sleep(0.08)

    if measured:
        avg_base = round(sum(measured) / len(measured), 1)
        print("------------------------------------------------------------------")
        print(f"💡 Gợi ý điền vào edge/.env:  BASELINE_EMPTY_CM={avg_base}")
        print(f"   (Ngưỡng báo có hàng mặc định: < {avg_base - OCCUPIED_MARGIN_CM:.1f} cm)")
    print("==================================================================")


def run_monitor(sensor: UltrasonicSensor, locker_ids: List[int], interval: float, once: bool):
    print("================================================================================")
    print("📡 GIÁM SÁT 4 CẢM BIẾN SIÊU ÂM HC-SR04 (TRIG chung = GPIO 5 / Pin 29)")
    print(f"   • Ngăn kiểm tra : {locker_ids}")
    print(f"   • Chế độ        : {'MOCK (Giả lập)' if sensor.mock_mode else 'PHẦN CỨNG THẬT (Raspberry Pi)'}")
    print(f"   • Ngưỡng chuẩn  : Rỗng = {BASELINE_EMPTY_CM:.1f} cm | Có hàng khi < {BASELINE_EMPTY_CM - OCCUPIED_MARGIN_CM:.1f} cm")
    if not once:
        print("   • Nhấn Ctrl+C để dừng và dọn GPIO sạch sẽ.")
    print("================================================================================")

    if sensor.mock_mode:
        # Provide illustrative mock values when dry-running on PC
        demo_vals = {1: 35.0, 2: 14.5, 3: 34.8, 4: 9.2}
        for lid in locker_ids:
            sensor.set_mock_distance(demo_vals.get(lid, 35.0), locker_id=lid)

    round_num = 0
    while True:
        round_num += 1
        ts = time.strftime("%H:%M:%S")
        print(f"\n[{ts}] Lượt đo #{round_num}")
        print(f"{'Ngăn':<7} {'Chân ECHO':<16} {'Khoảng cách':<14} {'Mức lấp đầy':<18} {'Trạng thái'}")
        print("-" * 76)

        for lid in locker_ids:
            e_pin = ULTRASONIC_ECHO_PINS[lid]
            phys = ECHO_PHYSICAL_PINS.get(lid, "?")
            dist = sensor.measure_distance_cm(locker_id=lid, samples=5, sample_delay_sec=0.015)
            base = sensor.baselines_cm.get(lid, BASELINE_EMPTY_CM)
            threshold = base - OCCUPIED_MARGIN_CM

            if dist is None:
                print(
                    f"#{lid:<6} GPIO {e_pin:<2} (Pin {phys:<2})  "
                    f"{'TIMEOUT':<14} {'[----------]  --%':<18} ❌ LỖI / KHÔNG PHẢN HỒI"
                )
            else:
                bar, pct = _fill_bar(dist, base)
                occupied = dist < threshold
                status = "📦 CÓ HÀNG (OCCUPIED)" if occupied else "⬜ TRỐNG (EMPTY)"
                print(
                    f"#{lid:<6} GPIO {e_pin:<2} (Pin {phys:<2})  "
                    f"{dist:>6.2f} cm      [{bar}] {pct:>3}%   {status}"
                )

            # 60ms quiet gap between sensors sharing TRIG to avoid acoustic crosstalk
            time.sleep(0.06)

        if once:
            break
        time.sleep(max(0.1, interval))


def main():
    parser = argparse.ArgumentParser(description="Test & calibrate 4x HC-SR04 ultrasonic sensors on Raspberry Pi")
    parser.add_argument("--lockers", default="1,2,3,4", help="Danh sách ngăn cần test (VD: 1,2,3,4 hoặc 1,2)")
    parser.add_argument("--once", action="store_true", help="Chỉ đo 1 lượt rồi thoát")
    parser.add_argument("--calibrate", action="store_true", help="Hiệu chuẩn chiều cao tủ rỗng (20 mẫu/ngăn)")
    parser.add_argument("--interval", type=float, default=0.5, help="Chu kỳ lặp lại tính bằng giây (mặc định: 0.5)")
    parser.add_argument("--mock", action="store_true", help="Chạy giả lập trên máy tính không cần Pi")
    args = parser.parse_args()

    locker_ids = _parse_locker_ids(args.lockers)
    use_mock = args.mock or MOCK_HARDWARE

    # Always force enabled=True when running this dedicated hardware test tool
    sensor = UltrasonicSensor(
        mock_mode=use_mock,
        baseline_empty_cm=BASELINE_EMPTY_CM,
        occupied_margin_cm=OCCUPIED_MARGIN_CM,
        enabled=True,
    )

    try:
        if args.calibrate:
            run_calibration(sensor, locker_ids)
        else:
            run_monitor(sensor, locker_ids, interval=args.interval, once=args.once)
    except KeyboardInterrupt:
        print("\n🛑 Đã dừng kiểm thử HC-SR04.")
    finally:
        if not use_mock:
            try:
                import RPi.GPIO as GPIO
                GPIO.cleanup()
                print("✅ Đã dọn GPIO sạch sẽ.")
            except Exception:
                pass


if __name__ == "__main__":
    main()
