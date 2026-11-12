# 🔌 Hướng Dẫn Lắp Chân Phần Cứng & Kiểm Thử (Raspberry Pi 4B)

Tài liệu chuẩn hóa toàn bộ sơ đồ đấu nối chân (Pinout) khớp 100% với [`edge/config.py`](edge/config.py) và [`edge/core/keypad.py`](edge/core/keypad.py), kèm quy trình cài đặt (`setup.sh`), kiểm thử từng linh kiện và vận hành toàn hệ thống (`run_all.sh`).

---

## ⚠️ 1. Nguyên Tắc An Toàn Điện Trước Khi Cắm Dây

1. **Luôn tắt nguồn hoàn toàn** (`sudo shutdown -h now` $\rightarrow$ đợi đèn xanh tắt hẳn $\rightarrow$ rút cáp USB-C) trước khi cắm hoặc rút bất kỳ dây GPIO nào.
2. **Phân biệt `GPIO (BCM)` và `Pin Vật Lý (1–40)`**:
   - **Pin Vật Lý** đếm từ `1` đến `40` trên 2 hàng chân của Raspberry Pi 4B (`Pin 1` là chân góc trong cùng bên trái gần khe thẻ nhớ/HDMI).
   - **GPIO (BCM)** là số hiệu lập trình trong [`edge/config.py`](edge/config.py).
3. **Nguồn cho 3 Servo**:
   - Nếu gắn **từ 2–3 Servo** (đặc biệt loại MG90S/MG996R có tải đẩy chốt), hãy cấp **nguồn ngoài 5V–2A/3A riêng** vào dây Đỏ (`VCC`) của Servo và **nối chung dây GND** nguồn ngoài với chân `GND` của Raspberry Pi để tránh sụt áp làm Pi tự reboot.
4. **Điện áp cho Load Cell HX711**: Cấp **`VCC = 3.3V`** (Pin 1 hoặc Pin 17) để tín hiệu `DT` xuất ra ở mức `3.3V`, an toàn cho chân GPIO của Pi.
5. **Điện áp cho LCD 1602 I2C**: Cấp **`VCC = 5V`** (Pin 2 hoặc Pin 4) để màn hình hiển thị sáng rõ.

---

## 📌 2. Bảng Sơ Đồ Đấu Nối Chi Tiết (Raspberry Pi 4B - 40-Pin Header)

| Module / Linh Kiện | Chân Trên Module | GPIO (BCM) | Pin Vật Lý (1–40) | Ghi Chú Kỹ Thuật |
| :--- | :--- | :--- | :--- | :--- |
| **LCD 1602 (I2C PCF8574)** | `VCC` | `5V` | **Pin 2** (hoặc Pin 4) | Phải dùng 5V để chữ rõ |
| | `GND` | `GND` | **Pin 6** | Chung mass |
| | `SDA` | **GPIO 2** (`SDA1`) | **Pin 3** | Bus I2C số 1 |
| | `SCL` | **GPIO 3** (`SCL1`) | **Pin 5** | Địa chỉ mặc định `0x27` |
| **Servo Ngăn 1** | Signal (Cam/Vàng) | **GPIO 17** | **Pin 11** | PWM 50Hz: `0°` = Khóa, `90°` = Mở |
| **Servo Ngăn 2** | Signal (Cam/Vàng) | **GPIO 27** | **Pin 13** | |
| **Servo Ngăn 3** | Signal (Cam/Vàng) | **GPIO 22** | **Pin 15** | |
| *(Nguồn 3 Servo)* | Đỏ (`VCC`) / Nâu (`GND`) | `5V` ngoài / `GND` | **Pin 14 / 20 / 34** (`GND`) | **Nối chung GND** nguồn ngoài & Pi |
| **Cân Load Cell (HX711)** | `VCC` | **`3.3V`** | **Pin 1** (hoặc Pin 17) | Bảo vệ chân GPIO mức 3.3V |
| | `GND` | `GND` | **Pin 9** (hoặc Pin 25) | |
| | `DT` (`DOUT`) | **GPIO 5** | **Pin 29** | Input dữ liệu 24-bit |
| | `SCK` (`PD_SCK`) | **GPIO 6** | **Pin 31** | Output xung clock |
| **Còi Buzzer** | `I/O` (hoặc chân `+`) | **GPIO 26** | **Pin 37** | `BUZZER_ACTIVE_HIGH = True` |
| | `GND` (hoặc chân `-`) | `GND` | **Pin 39** | Nếu module 3 chân: `VCC` $\rightarrow$ `3.3V` |
| **Keypad 4x4 (Hàng)** | `R1` (Hàng 1) | **GPIO 18** | **Pin 12** | 4 chân hàng |
| | `R2` (Hàng 2) | **GPIO 23** | **Pin 16** | |
| | `R3` (Hàng 3) | **GPIO 24** | **Pin 18** | |
| | `R4` (Hàng 4) | **GPIO 25** | **Pin 22** | |
| **Keypad 4x4 (Cột)** | `C1` (Cột 1) | **GPIO 12** | **Pin 32** | 4 chân cột (`PUD_DOWN`) |
| | `C2` (Cột 2) | **GPIO 16** | **Pin 36** | |
| | `C3` (Cột 3) | **GPIO 20** | **Pin 38** | |
| | `C4` (Cột 4) | **GPIO 21** | **Pin 40** | |
| **Camera CSI** | Cáp dải băng 15-pin | Cổng `CAMERA` | *(Giữa HDMI1 & Audio)* | Mặt tiếp xúc đồng hướng về cổng HDMI/nguồn |

### Đấu nối 4 dây từ Load Cell vào mạch khuếch đại HX711
- **Đỏ** $\rightarrow$ `E+`
- **Đen** $\rightarrow$ `E-`
- **Trắng** $\rightarrow$ `A-`
- **Xanh lá** $\rightarrow$ `A+`

---

## ⌨️ 3. Bảng Ánh Xạ Phím Keypad 4x4 (`S1`–`S16`)

Theo [`KEYPAD_MATRIX`](edge/core/keypad.py#L27-L34) *(đã bố trí 1–9 lên 9 ô đầu `S1`–`S9` và bỏ qua `S10` bị hỏng)*:

| | `C1` (GPIO 12) | `C2` (GPIO 16) | `C3` (GPIO 20) | `C4` (GPIO 21) |
| :--- | :---: | :---: | :---: | :---: |
| **`R1` (GPIO 18)** | `S1` = **`1`** | `S2` = **`2`** | `S3` = **`3`** | `S4` = **`4`** |
| **`R2` (GPIO 23)** | `S5` = **`5`** | `S6` = **`6`** | `S7` = **`7`** | `S8` = **`8`** |
| **`R3` (GPIO 24)** | `S9` = **`9`** | `S10` = *(Hỏng - Bỏ)* | `S11` = **`0`** | `S12` = **`C`** |
| **`R4` (GPIO 25)** | **`S13` = `*`** *(Quét gửi hàng)* | `S14` = **`0`** *(Dự phòng)* | **`S15` = `#`** *(Nhập OTP)* | `S16` = **`D`** |

- Bấm **`*` (`S13`)**: Khởi động Camera quét mã vận đơn (luồng Shipper gửi hàng) hoặc xóa lùi khi đang nhập OTP.
- Bấm **`#` (`S15`)**: Chuyển sang nhập **6 chữ số OTP** (`S1`–`S9`, `S11`/`S14`) để mở tủ lấy hàng.

---

## 🧪 4. Quy Trình Cài Đặt & Test Từng Linh Kiện

### Bước 1: Cài đặt tự động trên Raspberry Pi
```bash
cd ~/IOT/Smart-Parcel-Locker
chmod +x setup.sh run_all.sh
./setup.sh
```
Kích hoạt môi trường ảo trước khi chạy các lệnh test đơn lẻ bên dưới:
```bash
source .venv/bin/activate
export PYTHONPATH="."
```

### Bước 2: Test từng linh kiện độc lập *(nhớ tắt `./run_all.sh` trước để tránh lỗi `GPIO busy`)*

1. **Kiểm tra LCD 1602 (I2C)**:
   ```bash
   sudo i2cdetect -y 1
   python -c "from edge.hardware.indicators import IndicatorController; i=IndicatorController(mock_mode=False); i.display_message('Smart Locker','LCD OK!')"
   ```
   *(Nếu không cắm LCD, code tự in nội dung ra CLI dạng `[LCD Display] | ... | ... |` mà không bị lỗi).*

2. **Kiểm tra Buzzer**:
   ```bash
   python -c "from edge.hardware.indicators import IndicatorController; i=IndicatorController(mock_mode=False); i.success_sound(); i.alarm_sound(2); i.cleanup()"
   ```
   *(Nếu còi kêu liên tục ngay khi bật Pi, đổi `BUZZER_ACTIVE_HIGH = False` trong `edge/config.py`).*

3. **Kiểm tra 3 Servo chốt cửa**:
   ```bash
   python -c "from edge.hardware.lock_controller import LockController; l=LockController(mock_mode=False); [l.open_locker_door(k, 2.0) for k in (1,2,3)]; l.cleanup()"
   ```

4. **Kiểm tra Keypad 4x4**:
   ```bash
   python -c "import time; from edge.core.keypad import KeypadReader; kp=KeypadReader(mock_mode=False); t=time.time(); [print('Phim:', k) if (k:=kp.scan_single_key()) else None or time.sleep(0.05) for _ in range(300)]"
   ```

5. **Kiểm tra & Calibrate cân Load Cell HX711**:
   ```bash
   python -c "
   import time; from edge.hardware.hx711_loadcell import LoadCellController
   lc = LoadCellController(mock_mode=False); lc.tare(1)
   print('Dat vat mau len can...')
   for _ in range(15):
       raw, std = lc._read_filtered_hx711(samples=5)
       g = (raw - lc.tare_offsets[1]) / lc.calibration_factor
       print(f'{g:8.2f} g | raw={raw:.1f} | std={std:.1f}')
       time.sleep(0.4)
   "
   ```
   - Nếu đọc ra số âm $\rightarrow$ đổi dấu `LOADCELL_CALIBRATION_FACTOR` hoặc đảo `A+`/`A-`.
   - Công thức chuẩn hóa: $\text{Factor mới} = \text{Factor cũ} \times \frac{\text{Số gram đo được}}{\text{Số gram thật}}$.

6. **Kiểm tra Camera CSI & Quét mã**:
   ```bash
   rpicam-hello --list-cameras
   python edge/test/test_camera_scanner.py --mode raspberry
   ```

---

## 🚀 5. Chạy Toàn Bộ Hệ Thống

1. Điền `TELEGRAM_BOT_TOKEN` và `TELEGRAM_BOT_USERNAME` vào `server/.env` (nếu dùng Telegram Bot).
2. Chạy toàn bộ **FastAPI Server + Web Dashboard + Telegram Bot + Edge FSM** bằng 1 lệnh:
   ```bash
   ./run_all.sh
   ```
   *(Dùng `./run_all.sh --mock` để test qua bàn phím terminal mà chưa cần cắm mạch)*.
3. Mở Web Dashboard trên trình duyệt tại **`http://<IP_CỦA_PI>:8000`**.
4. Nhấn **`Ctrl + C`** trên terminal Pi để dừng sạch cả Server và Edge.

