# 🔌 Hướng Dẫn Lắp Chân Phần Cứng & Kiểm Thử (Raspberry Pi 4B — 4 Ngăn Tủ)

Tài liệu chuẩn hóa toàn bộ sơ đồ đấu nối chân (Pinout) cho hệ thống **4 ngăn tủ (Servo + HC-SR04 + Reed Switch + Keypad 4x4 + LCD I2C + Buzzer + Camera)**, khớp 100% với [`edge/config.py`](edge/config.py) và [`edge/core/keypad.py`](edge/core/keypad.py) (**0 xung đột chân GPIO**, đã kiểm tra bằng `validate_gpio_pinout()`).

---

## ⚠️ 1. Nguyên Tắc An Toàn Điện Trước Khi Cắm Dây

1. **Luôn tắt nguồn hoàn toàn** (`sudo shutdown -h now` → đợi đèn xanh ACT tắt hẳn → rút cáp USB-C) trước khi cắm hoặc rút bất kỳ dây GPIO nào.
2. **Phân biệt `GPIO (BCM)` và `Pin Vật Lý (1–40)`**:
   - **Pin Vật Lý** đếm từ `1` đến `40` trên 2 hàng chân của Raspberry Pi 4B (`Pin 1` là chân góc trong cùng bên trái gần khe thẻ nhớ/HDMI; `Pin 2` là chân `5V` sát mép ngoài).
   - **GPIO (BCM)** là số hiệu lập trình trong [`edge/config.py`](edge/config.py).
3. **Nguồn cho 4 Servo (`SG90` / `MG996R`)**:
   - **Điện áp chuẩn**: **4.8V – 6V** (dùng nguồn **5V**). **Tuyệt đối KHÔNG cấp nguồn > 6V** (như 7V/9V/12V sẽ cháy IC servo) và **KHÔNG lấy nguồn từ chân `3.3V`** của Pi.
   - **Khi chạy đủ 4 Servo có tải chốt cửa**: Dùng **nguồn ngoài 5V – 2A/3A riêng** cấp vào dây Đỏ (`VCC`) của các servo và **nối chung dây `GND`** của nguồn ngoài với chân `GND` của Pi (không nối dây `+5V` của nguồn ngoài vào chân `5V` của Pi).
   - *(Chỉ khi test không tải 1–2 con SG90 rời chưa gắn chốt cửa mới được lấy tạm từ Pin 2 / Pin 4 `5V` của Pi).*
4. **BẮT BUỘC dùng mạch chia áp `5V → 3.3V` cho 4 dây `ECHO` của HC-SR04**:
   - Cảm biến siêu âm HC-SR04 chạy nguồn `5V` nên chân `ECHO` xuất xung `5V`. Chân GPIO của Raspberry Pi chỉ chịu tối đa **`3.3V`** — nối thẳng `ECHO` vào Pi có thể gây chết chân GPIO!
   - **Cách mắc cầu chia áp cho mỗi dây `ECHO`**:
     ```text
     HC-SR04 ECHO (5V) ──[ 1kΩ ]──┬──> Pi GPIO ECHO (3.3V an toàn)
                                  │
                              [ 2kΩ ]
                                  │
                                 GND
     ```
5. **Điện áp cho LCD 1602 I2C**: Cấp **`VCC = 5V`** (Pin 2 hoặc Pin 4) để màn hình hiển thị sáng rõ.

---

## 📌 2. Bảng Sơ Đồ Đấu Nối Chi Tiết (Raspberry Pi 4B — 40-Pin Header)

> Tổng sử dụng **24 / 26 chân GPIO** (dư nguyên `GPIO 14` Pin 8 & `GPIO 15` Pin 10 cho UART), **không có bất kỳ cặp chân nào bị trùng**.

| Module / Linh Kiện | Chân Trên Module | GPIO (BCM) | Pin Vật Lý (1–40) | Ghi Chú Kỹ Thuật |
| :--- | :--- | :--- | :--- | :--- |
| **LCD 1602 (I2C PCF8574)** | `VCC` | `5V` | **Pin 2** (hoặc Pin 4) | Phải dùng 5V để chữ rõ |
| | `GND` | `GND` | **Pin 6** | Chung mass |
| | `SDA` | **GPIO 2** (`SDA1`) | **Pin 3** | Bus I2C số 1 |
| | `SCL` | **GPIO 3** (`SCL1`) | **Pin 5** | Địa chỉ mặc định `0x27` |
| **4x Servo Khóa Cửa** | **Servo Ngăn 1** (Cam/Vàng) | **GPIO 17** | **Pin 11** | PWM 50Hz: `0°` = Khóa, `90°` = Mở |
| | **Servo Ngăn 2** (Cam/Vàng) | **GPIO 27** | **Pin 13** | Tự ngắt xung (`duty=0`) chống rung |
| | **Servo Ngăn 3** (Cam/Vàng) | **GPIO 22** | **Pin 15** | |
| | **Servo Ngăn 4** (Cam/Vàng) | **GPIO 4** | **Pin 7** | |
| *(Nguồn 4 Servo)* | Đỏ (`VCC`) / Nâu (`GND`) | `5V` ngoài / `GND` | **Pin 14 / 20 / 34** (`GND`) | **Nối chung GND** nguồn ngoài & Pi |
| **4x Siêu Âm HC-SR04** | `VCC` / `GND` | `5V` / `GND` | **Pin 4** (`5V`) / **Pin 9** (`GND`) | Đo tuần tự từng ngăn |
| | `TRIG` *(Dùng chung 4 cảm biến)* | **GPIO 5** | **Pin 29** | Nối chung cả 4 chân `TRIG` về Pin 29 |
| | `ECHO 1` *(Ngăn 1)* | **GPIO 6** | **Pin 31** | **Qua cầu chia áp 1kΩ / 2kΩ** |
| | `ECHO 2` *(Ngăn 2)* | **GPIO 13** | **Pin 33** | **Qua cầu chia áp 1kΩ / 2kΩ** |
| | `ECHO 3` *(Ngăn 3)* | **GPIO 19** | **Pin 35** | **Qua cầu chia áp 1kΩ / 2kΩ** |
| | `ECHO 4` *(Ngăn 4)* | **GPIO 26** | **Pin 37** | **Qua cầu chia áp 1kΩ / 2kΩ** |
| **4x Công Tắc Cửa (Reed)** | **Cửa Ngăn 1** *(1 dây về GND)* | **GPIO 7** | **Pin 26** | Active LOW (`PUD_UP`), đóng cửa = nối GND |
| *(Tùy chọn)* | **Cửa Ngăn 2** *(1 dây về GND)* | **GPIO 8** | **Pin 24** | Có thể tắt bằng `ENABLE_DOOR_SWITCH=false` |
| | **Cửa Ngăn 3** *(1 dây về GND)* | **GPIO 9** | **Pin 21** | |
| | **Cửa Ngăn 4** *(1 dây về GND)* | **GPIO 11** | **Pin 23** | |
| **Còi Buzzer** | `I/O` (hoặc chân `+`) | **GPIO 10** | **Pin 19** | `BUZZER_ACTIVE_HIGH = True` |
| | `GND` (hoặc chân `-`) | `GND` | **Pin 25** (hoặc Pin 39) | Nếu module 3 chân: `VCC` → `3.3V` (Pin 1) |
| **Keypad 4x4 (Hàng)** | `R1` (Hàng 1) | **GPIO 18** | **Pin 12** | 4 chân hàng (Output) |
| | `R2` (Hàng 2) | **GPIO 23** | **Pin 16** | |
| | `R3` (Hàng 3) | **GPIO 24** | **Pin 18** | |
| | `R4` (Hàng 4) | **GPIO 25** | **Pin 22** | |
| **Keypad 4x4 (Cột)** | `C1` (Cột 1) | **GPIO 12** | **Pin 32** | 4 chân cột (Input, `PUD_DOWN`) |
| | `C2` (Cột 2) | **GPIO 16** | **Pin 36** | |
| | `C3` (Cột 3) | **GPIO 20** | **Pin 38** | |
| | `C4` (Cột 4) | **GPIO 21** | **Pin 40** | |
| **Camera CSI / USB** | Cáp dải băng 15-pin / USB | Cổng `CAMERA` / USB | *(Giữa HDMI1 & Audio)* | Dùng cho quét mã vận đơn & Face ID (`USE_CSI_CAMERA`) |

---

## ⌨️ 3. Bảng Ánh Xạ Phím Keypad 4x4 (`S1`–`S16`)

Theo [`KEYPAD_MATRIX`](edge/core/keypad.py#L27-L34) *(đã bố trí `1`–`9` lên 9 ô đầu `S1`–`S9` và bỏ qua `S10` bị hỏng)*:

| | `C1` (GPIO 12) | `C2` (GPIO 16) | `C3` (GPIO 20) | `C4` (GPIO 21) |
| :--- | :---: | :---: | :---: | :---: |
| **`R1` (GPIO 18)** | `S1` = **`1`** | `S2` = **`2`** | `S3` = **`3`** | `S4` = **`4`** |
| **`R2` (GPIO 23)** | `S5` = **`5`** | `S6` = **`6`** | `S7` = **`7`** | `S8` = **`8`** |
| **`R3` (GPIO 24)** | `S9` = **`9`** | `S10` = *(Hỏng - Bỏ)* | `S11` = **`0`** | `S12` = **`C`** |
| **`R4` (GPIO 25)** | **`S13` = `*`** *(Gửi hàng)* | `S14` = **`0`** *(Dự phòng)* | **`S15` = `#`** *(Nhập OTP)* | **`S16` = `D`** *(Face ID)* |

- Bấm **`*` (`S13`)**: Khởi động Camera quét mã vận đơn (luồng Shipper gửi hàng) hoặc xóa lùi khi đang nhập số.
- Bấm **`#` (`S15`)** *(hoặc bấm trực tiếp chữ số đầu tiên)*: Nhập **6 chữ số OTP** để mở tủ lấy hàng (hỗ trợ mở tất cả các đơn gộp chung ngăn tủ).
- Bấm **`D` (`S16`)**: Mở tủ bằng **Face ID** (nhập Account ID → nhấn `#` → quét khuôn mặt 5 góc qua Camera Pi).

---

## 🧪 4. Quy Trình Cài Đặt & Test Từng Linh Kiện

### Bước 1: Cài đặt tự động trên Raspberry Pi
```bash
cd ~/IOT/Smart-Parcel-Locker
chmod +x setup.sh run_all.sh
./setup.sh
```
`./setup.sh` sẽ tự động cài gói hệ thống (`openssl`, `i2c-tools`, `python3-rpi-lgpio`, `picamera2`, `tesseract-ocr`), tạo `.venv`, **tải 2 model Face ID ONNX (`YuNet` + `SFace`)** về `edge/models/face/`, và **tự sinh + đồng bộ `SECRET_KEY` & `FACE_DEVICE_KEY`** vào cả `server/.env` và `edge/.env`.

Kích hoạt môi trường ảo trước khi chạy các lệnh test đơn lẻ bên dưới:
```bash
source .venv/bin/activate
export PYTHONPATH="."
```

### Bước 2: Test từng linh kiện độc lập *(nhớ tắt `./run_all.sh` trước để tránh lỗi `GPIO busy`)*

1. **Kiểm tra không có xung đột chân GPIO**:
   ```bash
   python -c "from edge.config import validate_gpio_pinout; print('Conflicts:', validate_gpio_pinout())"
   ```

2. **Kiểm tra LCD 1602 (I2C)**:
   ```bash
   sudo i2cdetect -y 1
   python -c "from edge.hardware.indicators import IndicatorController; i=IndicatorController(mock_mode=False); i.display_message('Smart Locker','LCD OK!')"
   ```
   *(Nếu chưa cắm LCD, code tự in nội dung ra CLI dạng `[LCD Display] | ... | ... |` mà không bị lỗi).*

3. **Kiểm tra Buzzer (GPIO 10)**:
   ```bash
   python -c "from edge.hardware.indicators import IndicatorController; i=IndicatorController(mock_mode=False); i.success_sound(); i.alarm_sound(2); i.cleanup()"
   ```
   *(Nếu còi kêu liên tục ngay khi bật Pi, đổi `BUZZER_ACTIVE_HIGH = False` trong `edge/config.py`).*

4. **Kiểm tra 4 Servo chốt cửa (`ServoLockController`)**:
   ```bash
   python -c "import time; from edge.hardware.servo_lock import ServoLockController; l=ServoLockController(mock_mode=False); [ (l.unlock_door(k), time.sleep(1.0), l.lock_door(k), time.sleep(0.8)) for k in (1,2,3,4) ]; l.cleanup()"
   ```

5. **Kiểm tra & Calibrate 4 cảm biến siêu âm HC-SR04**:
   ```bash
   # Giám sát trực tiếp 4 cảm biến (hiển thị cm, % lấp đầy, Có hàng/Trống/Timeout)
   python scripts/test_ultrasonic.py

   # Chỉ test riêng 1 vài ngăn (VD: ngăn 1 & 2) hoặc đo 1 lượt
   python scripts/test_ultrasonic.py --lockers 1,2 --once

   # Hiệu chuẩn chiều cao tủ rỗng thực tế (20 mẫu/ngăn -> gợi ý BASELINE_EMPTY_CM)
   python scripts/test_ultrasonic.py --calibrate
   ```
   - Khi tủ rỗng, khoảng cách chuẩn mặc định là `BASELINE_EMPTY_CM=35.0` (chỉnh trong `edge/.env` theo chiều cao thực tế của tủ).
   - Khi có bưu kiện (`distance < baseline - OCCUPIED_MARGIN_CM`, mặc định `< 30.0 cm`), hệ thống xác nhận có hàng và khóa Servo.

6. **Kiểm tra nhanh Bàn phím 4x4 + 2 Servo 3, 4 (khi chưa lắp đủ mạch)**:
   ```bash
   python scripts/test_keypad_servo.py
   ```
   - Để chạy thử toàn hệ thống `./run_all.sh` khi mới chỉ cắm Keypad + 2 Servo 3, 4 (chưa cắm HC-SR04 / Reed Switch):
     ```bash
     python scripts/test_keypad_servo.py --prep-full
     ./run_all.sh --https
     ```
   - Khi đã lắp hoàn chỉnh cả 4 tủ & cảm biến, chạy lệnh khôi phục:
     ```bash
     python scripts/test_keypad_servo.py --restore-full
     ```

7. **Kiểm tra Camera CSI & Quét mã**:
   ```bash
   rpicam-hello --list-cameras
   python edge/test/test_camera_scanner.py --mode raspberry
   ```

---

## 🚀 5. Chạy Toàn Bộ Hệ Thống

1. *(Tùy chọn)* Điền `TELEGRAM_BOT_TOKEN` vào `server/.env` nếu muốn nhận thông báo OTP qua Telegram Bot.
2. *(Tùy chọn)* Nếu mô hình chưa gắn 4 công tắc từ Reed Switch, đặt `ENABLE_DOOR_SWITCH=false` trong `edge/.env`.
3. Chạy toàn bộ **FastAPI Server + Web Portal (HTTPS cho Camera Face ID) + Telegram Bot + Edge FSM** bằng 1 lệnh:
   ```bash
   ./run_all.sh --https
   ```
   *(Hoặc `./run_all.sh --mock --https` để test CLI không cần cắm linh kiện).*
4. Truy cập giao diện Web trên điện thoại / laptop cùng mạng Wi-Fi:
   - **Cổng Người Dùng (Camera Face ID)**: `https://<IP_CỦA_PI>:8443/portal` *(chấp nhận chứng chỉ tự ký lần đầu)*
   - **Bảng Quản Trị Admin**: `http://<IP_CỦA_PI>:8000/login`
5. Nhấn **`Ctrl + C`** trên terminal Pi để dừng sạch cả Server và Edge và tự động dọn dẹp GPIO.
