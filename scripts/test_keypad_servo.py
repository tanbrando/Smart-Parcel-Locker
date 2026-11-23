#!/usr/bin/env python3
"""
Interactive Hardware Test Script: 4x4 Matrix Keypad + Servos #3 & #4.
Also includes --prep-full and --restore-full helpers to run `./run_all.sh`
in Partial Hardware Mode (only Keypad + Servos 3 & 4 wired).

Usage on Raspberry Pi:
  python scripts/test_keypad_servo.py              # Interactive test (Keypad + Servo 3 & 4)
  python scripts/test_keypad_servo.py --prep-full  # Configure .env & DB to run ./run_all.sh with Lockers 3 & 4
  python scripts/test_keypad_servo.py --restore-full # Restore full 4-locker & sensors config
"""
import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from contracts.schemas import LockState, LockerStatus, OrderStatus
from edge.config import (
    KEYPAD_COL_PINS,
    KEYPAD_ROW_PINS,
    LOCKER_SERVO_PINS,
    MOCK_HARDWARE,
)
from edge.core.keypad import KEYPAD_MATRIX, KeypadReader
from edge.hardware.servo_lock import ServoLockController


def _upsert_env(env_path: Path, updates: dict):
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    seen = set()
    out = []
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k = s.split("=", 1)[0].strip()
            if k in updates:
                out.append(f"{k}={updates[k]}")
                seen.add(k)
                continue
        out.append(line)
    for k, v in updates.items():
        if k not in seen:
            out.append(f"{k}={v}")
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def prepare_full_partial_mode():
    """Configures edge/.env and SQLite DB so `./run_all.sh` uses Keypad + Servos 3 & 4 only."""
    edge_env = REPO_ROOT / "edge" / ".env"
    if not edge_env.exists() and (REPO_ROOT / "edge" / ".env.example").exists():
        edge_env.write_text((REPO_ROOT / "edge" / ".env.example").read_text(encoding="utf-8"), encoding="utf-8")

    _upsert_env(
        edge_env,
        {
            "MOCK_HARDWARE": "false",
            "CAMERA_MODE": "test",
            "ENABLE_DOOR_SWITCH": "false",
            "ENABLE_ULTRASONIC": "false",
            "ACTIVE_LOCKER_IDS": "3,4",
        },
    )

    from server.main import init_database_tables
    from server.db.session import SessionLocal
    from server.db.models import Locker, Order, User

    init_database_tables()
    db = SessionLocal()
    try:
        # Put Lockers 1 & 2 into MAINTENANCE, ensure Lockers 3 & 4 are EMPTY
        for locker in db.query(Locker).all():
            if locker.locker_number in (1, 2):
                locker.status = LockerStatus.MAINTENANCE
            elif locker.locker_number in (3, 4):
                locker.status = LockerStatus.EMPTY
                locker.current_weight = 0
                locker.current_distance_cm = locker.empty_distance_cm or 35.0

        # Ensure a sample REGISTERED order exists matching edge/test/cameras/shopee.jpg
        sample_tracking = "SPXVN048291048"
        user = db.query(User).filter(User.role == "USER").first() or db.query(User).first()
        existing = db.query(Order).filter(Order.tracking_number == sample_tracking).first()
        if user and not existing:
            db.add(
                Order(
                    user_id=user.id,
                    tracking_number=sample_tracking,
                    order_code="TEST-DEMO-01",
                    expected_weight=500,
                    status=OrderStatus.REGISTERED,
                )
            )
        elif existing and existing.status != OrderStatus.REGISTERED:
            existing.status = OrderStatus.REGISTERED
            existing.locker_id = None
            existing.otp_code = None

        db.commit()
    finally:
        db.close()

    print("==========================================================")
    print("✅ ĐÃ CẤU HÌNH XONG CHẾ ĐỘ CHẠY FULL (CHỈ KEYPAD + SERVO 3 & 4)")
    print("   • edge/.env: MOCK_HARDWARE=false, CAMERA_MODE=test,")
    print("                ENABLE_ULTRASONIC=false, ENABLE_DOOR_SWITCH=false, ACTIVE_LOCKER_IDS=3,4")
    print("   • Database : Ngăn #1 & #2 -> MAINTENANCE | Ngăn #3 & #4 -> EMPTY")
    print("   • Đơn mẫu  : SPXVN048291048 (REGISTERED - khớp ảnh test camera)")
    print("")
    print("👉 Bây giờ chạy:  ./run_all.sh --https")
    print("   1. Bấm '*' trên Keypad -> Servo 3 mở -> 4s sau Servo 3 tự khóa & sinh OTP")
    print("   2. Xem mã OTP trên Web Portal (/portal) hoặc log terminal")
    print("   3. Bấm 6 số OTP trên Keypad thật -> Servo 3 tự động mở ra!")
    print("==========================================================")


def restore_full_mode():
    """Restores full 4-locker & sensor config in edge/.env and SQLite DB."""
    edge_env = REPO_ROOT / "edge" / ".env"
    _upsert_env(
        edge_env,
        {
            "MOCK_HARDWARE": "false",
            "CAMERA_MODE": "raspberry",
            "ENABLE_DOOR_SWITCH": "true",
            "ENABLE_ULTRASONIC": "true",
            "ACTIVE_LOCKER_IDS": "1,2,3,4",
        },
    )
    from server.main import init_database_tables
    from server.db.session import SessionLocal
    from server.db.models import Locker

    init_database_tables()
    db = SessionLocal()
    try:
        for locker in db.query(Locker).all():
            locker.status = LockerStatus.EMPTY
            locker.current_weight = 0
            locker.current_distance_cm = locker.empty_distance_cm or 35.0
        db.commit()
    finally:
        db.close()

    print("✅ Đã khôi phục cấu hình đầy đủ 4 ngăn tủ (#1-#4) + HC-SR04 + Reed Switch.")


def _find_key_coords(key_char: str):
    for r_idx, row in enumerate(KEYPAD_MATRIX):
        for c_idx, val in enumerate(row):
            if val == key_char:
                return r_idx, c_idx
    return None, None


def run_interactive_hardware_test(force_mock: bool = False):
    use_mock = force_mock or MOCK_HARDWARE
    print("==========================================================")
    print("🔧 TEST PHẦN CỨNG: KEYPAD 4x4 + SERVO NGĂN 3 & NGĂN 4")
    print(f"   • Chế độ    : {'MOCK' if use_mock else 'PHẦN CỨNG THẬT (Raspberry Pi)'}")
    print(f"   • Servo 3   : GPIO {LOCKER_SERVO_PINS[3]} (Pin 15)")
    print(f"   • Servo 4   : GPIO {LOCKER_SERVO_PINS[4]} (Pin 7)")
    print(f"   • Keypad R  : {KEYPAD_ROW_PINS} (Pin 12, 16, 18, 22)")
    print(f"   • Keypad C  : {KEYPAD_COL_PINS} (Pin 32, 36, 38, 40)")
    print("----------------------------------------------------------")
    print("👉 Hướng dẫn bấm trên Bàn phím 4x4:")
    print("   [3] : Đảo MỞ (90°) <-> KHÓA (0°) cho Servo 3")
    print("   [4] : Đảo MỞ (90°) <-> KHÓA (0°) cho Servo 4")
    print("   [*] : Quét thử tuần tự Servo 3 rồi Servo 4")
    print("   [#] : Nhập thử OTP 6 số ('333333' mở Servo 3, '444444' mở Servo 4)")
    print("   Phím bất kỳ khác: In tên phím + chân Hàng/Cột để kiểm tra dây")
    print("   Nhấn Ctrl+C để thoát an toàn.")
    print("==========================================================")

    lock = ServoLockController(mock_mode=use_mock, active_lockers=[3, 4])
    keypad = KeypadReader(mock_mode=use_mock)

    def toggle_servo(locker_id: int):
        if lock.get_lock_state(locker_id) == LockState.UNLOCKED:
            lock.lock_door(locker_id)
            print(f"   🔒 Servo {locker_id} (GPIO {LOCKER_SERVO_PINS[locker_id]}) -> KHÓA (0°)")
        else:
            lock.unlock_door(locker_id)
            print(f"   🔓 Servo {locker_id} (GPIO {LOCKER_SERVO_PINS[locker_id]}) -> MỞ (90°)")

    try:
        if use_mock:
            print("(Đang ở chế độ MOCK - nhập 3, 4, *, #, hoặc q trên bàn phím máy tính)")
            while True:
                cmd = input("Mock Key > ").strip().upper()
                if cmd in ("Q", "QUIT", "EXIT"):
                    break
                if cmd == "3":
                    toggle_servo(3)
                elif cmd == "4":
                    toggle_servo(4)
                elif cmd == "*":
                    for lid in (3, 4):
                        lock.unlock_door(lid)
                        time.sleep(0.5)
                        lock.lock_door(lid)
                elif cmd == "#":
                    pin = input("Nhập 6 số OTP thử (333333 hoặc 444444): ").strip()
                    if pin == "333333":
                        lock.unlock_door(3)
                    elif pin == "444444":
                        lock.unlock_door(4)
                    else:
                        print(f"   ❌ OTP '{pin}' không khớp (thử 333333 hoặc 444444).")
                else:
                    print(f"   Nhận phím: {cmd}")
        else:
            while True:
                key = keypad.scan_single_key()
                if key:
                    r_idx, c_idx = _find_key_coords(key)
                    if r_idx is not None:
                        print(
                            f"⌨️  Phím '{key}' | R{r_idx+1}(GPIO {KEYPAD_ROW_PINS[r_idx]}) "
                            f"x C{c_idx+1}(GPIO {KEYPAD_COL_PINS[c_idx]})"
                        )
                    else:
                        print(f"⌨️  Phím '{key}'")

                    if key == "3":
                        toggle_servo(3)
                    elif key == "4":
                        toggle_servo(4)
                    elif key == "C":
                        closed = lock.lock_all_open_doors()
                        print(f"   🔒 Phím 'C' -> Đã khóa các ngăn đang mở: {closed or 'Không có ngăn nào mở'}")
                    elif key == "*":
                        print("   🔄 Test tuần tự Servo 3 -> Servo 4...")
                        for lid in (3, 4):
                            lock.unlock_door(lid)
                            time.sleep(1.0)
                            lock.lock_door(lid)
                            time.sleep(0.8)
                    elif key == "#":
                        print("   🔢 Nhập 6 số OTP trên Keypad (333333 mở Tủ 3, 444444 mở Tủ 4)...")
                        pin = keypad.get_pin_input(timeout=20.0, max_digits=6)
                        print(f"   📩 Đã nhận OTP: '{pin}'")
                        if pin == "333333":
                            lock.unlock_door(3)
                            print("   ✅ Khớp 333333 -> Đã MỞ Servo 3!")
                        elif pin == "444444":
                            lock.unlock_door(4)
                            print("   ✅ Khớp 444444 -> Đã MỞ Servo 4!")
                        else:
                            print("   ❌ Sai mã thử (dùng 333333 hoặc 444444).")
                time.sleep(0.05)
    except KeyboardInterrupt:
        print("\n🛑 Đang dừng và dọn dẹp GPIO...")
    finally:
        lock.cleanup()
        if not use_mock:
            try:
                import RPi.GPIO as GPIO
                GPIO.cleanup()
            except Exception:
                pass
        print("✅ Đã dọn GPIO sạch sẽ.")


def main():
    parser = argparse.ArgumentParser(description="Test Keypad 4x4 & Servos 3, 4 on Raspberry Pi")
    parser.add_argument("--prep-full", action="store_true", help="Cấu hình .env & DB để chạy ./run_all.sh chỉ với Keypad + Servo 3, 4")
    parser.add_argument("--restore-full", action="store_true", help="Khôi phục cấu hình đầy đủ 4 ngăn tủ & cảm biến")
    parser.add_argument("--mock", action="store_true", help="Chạy thử ở chế độ giả lập trên máy tính")
    args = parser.parse_args()

    if args.prep_full:
        prepare_full_partial_mode()
    elif args.restore_full:
        restore_full_mode()
    else:
        run_interactive_hardware_test(force_mock=args.mock)


if __name__ == "__main__":
    main()
