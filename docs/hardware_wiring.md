# 🔌 Sơ đồ đấu dây & Hướng dẫn phần cứng: Cảm biến siêu âm & Servo khoá cửa

Tài liệu này hướng dẫn chi tiết cách đấu dây phần cứng, nguyên lý hoạt động, và cách hiệu chuẩn cảm biến siêu âm trên **Raspberry Pi 4B** theo thiết kế mới tại [TASK_ultrasonic_servo.md](file:///c:/KOUPC/study/5th/IOT/code/Smart-Parcel-Locker/TASK_ultrasonic_servo.md).

---

## 📌 1. Bảng phân bổ chân GPIO (Raspberry Pi 4B)

Tất cả chân GPIO được cấu hình tập trung trong file [edge/config.py](file:///c:/KOUPC/study/5th/IOT/code/Smart-Parcel-Locker/edge/config.py):

| Linh kiện | Chân tín hiệu | Chân Raspberry Pi 4B (BCM) | Ghi chú kỹ thuật |
| :--- | :--- | :--- | :--- |
| **Servo Ngăn 1 (SG90/MG996R)** | `PWM Signal` (Vàng/Cam) | **GPIO 17** (Pin 11) | Tần số 50Hz. $0^\circ$ = Khóa, $90^\circ$ = Mở. |
| **Servo Ngăn 2** | `PWM Signal` | **GPIO 27** (Pin 13) | Tần số 50Hz |
| **Servo Ngăn 3** | `PWM Signal` | **GPIO 22** (Pin 15) | Tần số 50Hz |
| **Servo Ngăn 4** | `PWM Signal` | **GPIO 4** (Pin 7) | Tần số 50Hz |
| **Công tắc từ cửa (Reed switch) 1** | `DOOR_SWITCH` | **GPIO 23** (Pin 16) | Nối GND khi cửa đóng (`PULL-UP` nội bộ kích hoạt) |
| **Công tắc từ cửa 2** | `DOOR_SWITCH` | **GPIO 24** (Pin 18) | Nối GND khi cửa đóng |
| **Công tắc từ cửa 3** | `DOOR_SWITCH` | **GPIO 25** (Pin 22) | Nối GND khi cửa đóng |
| **Công tắc từ cửa 4** | `DOOR_SWITCH` | **GPIO 7** (Pin 26) | Nối GND khi cửa đóng |
| **Siêu âm 1 (HC-SR04)** | `TRIG` | **GPIO 5** (Pin 29) | Xung 10µs kích sóng siêu âm |
| **Siêu âm 1 (HC-SR04)** | `ECHO` | **GPIO 6** (Pin 31) | **Bắt buộc dùng cầu chia áp 5V -> 3.3V** |
| **Siêu âm 2** | `TRIG` / `ECHO` | **GPIO 19** / **GPIO 20** | Cầu chia áp cho ECHO |
| **Siêu âm 3** | `TRIG` / `ECHO` | **GPIO 13** / **GPIO 16** | Cầu chia áp cho ECHO |
| **Siêu âm 4** | `TRIG` / `ECHO` | **GPIO 8** / **GPIO 9** | Cầu chia áp cho ECHO |
| **Màn hình LCD 1602 I2C** | `SDA` / `SCL` | **GPIO 2** (Pin 3) / **GPIO 3** (Pin 5) | Địa chỉ I2C: `0x27` (Bus 1) |
| **Còi Buzzer** | `I/O (+)` | **GPIO 26** (Pin 37) | Bíp báo trạng thái / Báo động |

---

## ⚠️ 2. Cảnh báo an toàn phần cứng quan trọng

### 2.1. Cầu chia áp cho chân ECHO của cảm biến HC-SR04
Cảm biến HC-SR04 chạy nguồn **5V**, do đó chân **ECHO** phát tín hiệu mức cao là **5V**. Chân GPIO của Raspberry Pi chỉ chịu được tối đa **3.3V**. Nếu nối trực tiếp sẽ làm hỏng chân GPIO hoặc cháy chip Broadcom trên Pi.

**Sơ đồ cầu phân áp (dùng 2 điện trở $1\text{ k}\Omega$ và $2\text{ k}\Omega$):**
```text
HC-SR04 (ECHO) ────[ R1 = 1 kΩ ]────┬────> Chân GPIO Pi (GPIO 6)  (~ 3.3V)
                                    │
                                 [ R2 = 2 kΩ ]
                                    │
                                   GND
```
$$V_{\text{out}} = 5\text{V} \times \frac{2\text{ k}\Omega}{1\text{ k}\Omega + 2\text{ k}\Omega} = 3.33\text{V} \quad \text{(An toàn tuyệt đối cho Pi)}$$

### 2.2. Nguồn cấp cho Servo
- **SG90 (nhỏ):** Có thể lấy nguồn 5V từ chân Pin 2 hoặc 4 của Pi khi thử nghiệm 1 servo.
- **MG996R (lực kéo lớn) hoặc nhiều servo:** **Bắt buộc dùng nguồn ngoài 5V (tối thiểu 2A - 3A)** cấp vào dây đỏ của Servo. Nhớ **nối chung cực âm (GND)** của nguồn ngoài với GND của Raspberry Pi.

---

## 🧠 3. Cơ chế hoạt động & Quyết định khóa cửa (`lock_if_occupied`)

Quy tắc nghiệp vụ:
1. **Tủ trống:** Servo ở trạng thái **UNLOCKED** (mở chốt). Cửa không bị khóa để sẵn sàng sử dụng.
2. **Shipper gửi hàng:**
   * Shipper mở cửa, đặt hàng vào trong, sau đó **đóng cửa tủ lại**.
   * Hệ thống kiểm tra:
     * Cửa đã đóng chưa? (`is_door_closed()`) $\rightarrow$ Nếu chưa đóng: **không khóa** (`LockDecision.DOOR_OPEN`).
     * Có hàng bên trong không? (`is_locker_occupied()`) $\rightarrow$ Đo khoảng cách bằng siêu âm.
     * **Cửa đóng + Có hàng:** $\rightarrow$ Servo quay về góc $0^\circ$ để **KHÓA CHỐT** (`LockDecision.LOCKED`).
     * **Cửa đóng + Tủ trống (Shipper không bỏ hàng):** $\rightarrow$ Giữ nguyên **UNLOCKED** (`LockDecision.EMPTY_NOT_LOCKED`) để FSM cảnh báo/hủy phiên.
3. **Người nhận lấy hàng:**
   * Nhập OTP hoặc nhận diện khuôn mặt đúng $\rightarrow$ Servo quay góc $90^\circ$ mở chốt (`unlock_door()`).
   * Khách lấy hàng xong, đóng cửa tủ lại $\rightarrow$ Cảm biến siêu âm thấy tủ trống $\rightarrow$ Giữ nguyên trạng thái **UNLOCKED** sẵn sàng cho đơn tiếp theo.

---

## 🛠️ 4. Hướng dẫn Hiệu chuẩn (Calibration) Cảm biến siêu âm

Khi lắp cảm biến trên trần tủ hướng xuống đáy:

1. Dọn sạch đồ bên trong tủ để tủ hoàn toàn trống.
2. Chạy lệnh hiệu chuẩn sau trên Raspberry Pi:
   ```bash
   python3 -c "from edge.hardware.ultrasonic_sensor import calibrate_empty_baseline; print('Baseline:', calibrate_empty_baseline(1, samples=20), 'cm')"
   ```
3. Lấy giá trị in ra (ví dụ: `35.2` cm) và cập nhật biến `BASELINE_EMPTY_CM` trong `edge/config.py` hoặc truyền qua file môi trường `.env`:
   ```bash
   BASELINE_EMPTY_CM=35.0
   OCCUPIED_MARGIN_CM=5.0
   ```
   *(Ngưỡng phát hiện hàng: Bất kỳ khoảng cách nào $< 35.0 - 5.0 = 30.0\text{ cm}$ sẽ được kết luận là CÓ HÀNG).*
