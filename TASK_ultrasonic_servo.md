# 📋 Mô tả công việc: Cảm biến siêu âm & Servo khoá cửa

**Module:** `edge/hardware/`
**Dự án:** Smart Parcel Locker (IoT)
**Người phụ trách:** _(điền tên)_
**Phối hợp với:** Person 1 (CV), Person 3 (FSM / `edge/core/`), Person 4 (Server)

---

## 1. Bối cảnh thay đổi so với thiết kế ban đầu

| Hạng mục | Thiết kế cũ | Thiết kế mới |
|---|---|---|
| Phát hiện hàng trong tủ | Load cell HX711 (đo chênh lệch cân nặng, chống gian lận) | **Cảm biến siêu âm** đo khoảng cách để biết tủ **có hàng / trống** |
| Khoá cửa | Solenoid + relay, mở khi có tín hiệu | **Động cơ servo**: tủ trống thì **không khoá**; shipper đóng cửa mà có hàng thì **tự khoá** |
| Xác thực | OTP + keypad | Thêm **nhận diện khuôn mặt** (Person 1 phụ trách, phần của tôi chỉ cần nhận lệnh mở/khoá) |

> **Hệ quả:** `hx711_loadcell.py` và `lock_controller.py` (solenoid) được thay bằng hai file mới bên dưới. Việc so khớp cân nặng khai báo với cân nặng thực tế không còn nữa. Server và FSM chỉ còn xác nhận "có hàng hay không".

---

## 2. Phạm vi công việc

### 2.1. Cảm biến siêu âm (phát hiện có hàng)
- Đọc khoảng cách từ cảm biến siêu âm (HC-SR04 hoặc JSN-SR04T) gắn trên trần tủ, hướng xuống đáy.
- **Hiệu chuẩn (calibration):** đo khoảng cách khi tủ trống làm mốc `baseline_empty_cm`, lưu vào `config.py`.
- Lọc nhiễu: lấy N mẫu (ví dụ 5–7), dùng **median**, loại bỏ giá trị ngoài vùng hợp lệ hoặc timeout.
- Kết luận **có hàng** khi `distance < baseline_empty_cm - OCCUPIED_MARGIN_CM`.
- Chống nhấp nháy (debounce): kết quả phải ổn định qua nhiều lần đọc liên tiếp mới trả về.

### 2.2. Servo khoá cửa
- Điều khiển servo (SG90 / MG996R) ở hai vị trí: **LOCKED** và **UNLOCKED** (góc cấu hình trong `config.py`).
- Logic nghiệp vụ:

| Tình huống | Hành động servo |
|---|---|
| Tủ trống, ở trạng thái chờ | **UNLOCKED** (không khoá) |
| Server cho phép shipper gửi hàng | Giữ / chuyển **UNLOCKED** để cửa mở được |
| Shipper đóng cửa, siêu âm báo **có hàng** | **LOCKED** |
| Shipper đóng cửa, siêu âm báo **trống** (không bỏ hàng) | Giữ **UNLOCKED**, báo lên FSM để xử lý (huỷ phiên / cảnh báo) |
| Người nhận nhập đúng OTP (hoặc khuôn mặt hợp lệ) | **UNLOCKED** |
| Người nhận lấy hàng xong, cửa đóng, tủ trống | Giữ **UNLOCKED**, tủ trở về trạng thái sẵn sàng |

- Tránh rung servo (jitter) và tránh servo giữ lực liên tục khi không cần: gửi xung xong thì ngắt xung (detach) sau khoảng 0.5 s.

### 2.3. Phát hiện đóng cửa
Logic "shipper đóng cửa rồi mới khoá" cần biết trạng thái cửa. Đề xuất dùng **công tắc từ (reed switch) hoặc limit switch** đọc qua GPIO.
- Hàm `is_door_closed() -> bool` đặt trong `servo_lock.py`.
- **Cần thống nhất với nhóm** (xem mục 7) xem có thêm cảm biến này không, vì thiết kế hiện tại chưa có.

### 2.4. Tích hợp Mock cho môi trường không có Raspberry Pi
- Khi không chạy trên Pi (import `RPi.GPIO` / `pigpio` lỗi) thì tự động dùng **Mock** để nhóm vẫn chạy `python main.py` và `pytest` được trên laptop.
- Mock cho phép giả lập: khoảng cách (qua biến hoặc hàm `set_mock_distance()`), trạng thái cửa, trạng thái servo.

---

## 3. Sản phẩm bàn giao (Deliverables)

| File | Nội dung |
|---|---|
| `edge/hardware/ultrasonic_sensor.py` | Đọc khoảng cách, lọc nhiễu, hiệu chuẩn, `is_locker_occupied()` |
| `edge/hardware/servo_lock.py` | Điều khiển servo, `lock_door()`, `unlock_door()`, `is_door_closed()`, `get_lock_state()` |
| `edge/hardware/indicators.py` | Cập nhật thông báo LCD/Buzzer cho các trạng thái mới (đã khoá, mở khoá, tủ trống) _(phối hợp, nếu cần)_ |
| `edge/config.py` | Thêm các tham số: chân GPIO, góc servo, baseline, ngưỡng |
| `contracts/schemas.py` | Thêm schema cho kết quả đo (xem mục 4.3) |
| `contracts/mock_data.py` | Thêm dữ liệu giả cho cảm biến và servo |
| `tests/test_edge_hardware.py` | Unit test cho logic chiếm chỗ, debounce, trạng thái khoá |
| `docs/hardware_wiring.md` | Sơ đồ đấu dây, thông số, cách hiệu chuẩn _(kèm ảnh/ sơ đồ)_ |

---

## 4. Giao diện (Interface) với các module khác

### 4.1. Hàm cung cấp cho Person 3 (FSM)

```python
# edge/hardware/ultrasonic_sensor.py
def measure_distance_cm(samples: int = 5) -> float | None:
    """Trả về khoảng cách (cm) đã lọc median, hoặc None nếu đo lỗi."""

def calibrate_empty_baseline(samples: int = 20) -> float:
    """Đo khi tủ trống, trả về baseline (cm) để lưu vào config."""

def is_locker_occupied() -> OccupancyResult:
    """Kết luận tủ có hàng hay không (đã debounce)."""
```

```python
# edge/hardware/servo_lock.py
def unlock_door() -> bool:      # True nếu servo đã về vị trí UNLOCKED
def lock_door() -> bool:        # True nếu servo đã về vị trí LOCKED
def is_door_closed() -> bool:   # đọc reed switch / limit switch
def get_lock_state() -> LockState   # LOCKED | UNLOCKED
```

### 4.2. Hàm tiện ích kết hợp (đề xuất)

```python
def lock_if_occupied() -> LockDecision:
    """
    Gọi sau khi shipper đóng cửa.
    - Cửa chưa đóng           -> LockDecision.DOOR_OPEN (không làm gì)
    - Cửa đóng, có hàng       -> lock_door(), trả LockDecision.LOCKED
    - Cửa đóng, không có hàng -> giữ unlock, trả LockDecision.EMPTY_NOT_LOCKED
    """
```

### 4.3. Schema đề xuất (đưa vào `contracts/schemas.py`)

```python
class LockState(str, Enum):
    LOCKED = "LOCKED"
    UNLOCKED = "UNLOCKED"

class OccupancyResult(BaseModel):
    occupied: bool
    distance_cm: float | None
    baseline_cm: float
    confidence: float          # 0..1, dựa trên độ ổn định của các mẫu
    error: str | None = None   # ví dụ "SENSOR_TIMEOUT"

class LockDecision(str, Enum):
    LOCKED = "LOCKED"
    EMPTY_NOT_LOCKED = "EMPTY_NOT_LOCKED"
    DOOR_OPEN = "DOOR_OPEN"
```

### 4.4. Luồng FSM mới (để Person 3 tham khảo)

```text
IDLE (tủ trống, servo UNLOCKED)
  -> SCANNING (CV đọc nhãn vận đơn)
  -> UNLOCKED (server duyệt, cho phép mở cửa)
  -> WAIT_DOOR_CLOSE (chờ shipper đặt hàng và đóng cửa)
  -> CHECK_OCCUPANCY (gọi is_locker_occupied())
       ├─ có hàng   -> lock_door() -> CONFIRM_DEPOSIT (gửi server) -> LOCKED_WAIT_PICKUP
       └─ không hàng -> giữ UNLOCKED -> huỷ phiên / cảnh báo -> IDLE
LOCKED_WAIT_PICKUP
  -> (OTP hoặc khuôn mặt hợp lệ) unlock_door() -> WAIT_DOOR_CLOSE
  -> CHECK_OCCUPANCY (trống) -> DONE -> IDLE
```

---

## 5. Yêu cầu kỹ thuật & lưu ý phần cứng

**Cảm biến siêu âm**
- HC-SR04 chạy ở **5 V**, chân **ECHO ra 5 V**, không nối thẳng vào GPIO của Pi (chỉ chịu 3.3 V). Dùng **cầu chia áp** (ví dụ 1 kΩ / 2 kΩ) hoặc module level shifter.
- Cảm biến có **vùng mù** gần (khoảng 2 cm), nên gắn sao cho khoảng cách tới hàng luôn lớn hơn vùng này.
- Kích thước tủ nhỏ gây phản xạ nhiều: kiểm tra với hàng có bề mặt mềm (túi nilon, hộp xốp), vì chúng hấp thụ/phản xạ âm kém. Nếu cần, thử JSN-SR04T hoặc đổi vị trí lắp.
- Ghi lại baseline và ngưỡng trong `config.py`, **không hard-code** trong hàm.

**Servo**
- **Không cấp nguồn servo từ chân 5 V của Pi** nếu dùng MG996R (dòng cao). Dùng nguồn 5 V ngoài, **nối chung GND** với Pi.
- Dùng thư viện `pigpio` (PWM phần cứng/DMA) để giảm rung so với `RPi.GPIO.PWM` thuần phần mềm.
- Cơ khí: chốt khoá gắn trên trục servo phải chịu được lực kéo của cửa; kiểm tra chốt không bị kẹt khi cửa đóng lệch.

**An toàn & độ tin cậy**
- Nếu cảm biến siêu âm lỗi / timeout liên tục: **không khoá** (fail-safe mở) và báo lỗi lên FSM → Server → Telegram cho admin.
- Ghi log mỗi lần đo và mỗi lần đổi trạng thái khoá để phục vụ debug và demo.

---

## 6. Tiêu chí nghiệm thu (Acceptance Criteria)

- [ ] Tủ trống, đo 20 lần liên tiếp đều trả `occupied = False`.
- [ ] Đặt các loại vật (hộp carton, túi nilon, hộp xốp) ở các vị trí khác nhau trong tủ, độ chính xác phát hiện **≥ 95%** trên ít nhất 20 lần thử.
- [ ] Servo mở/khoá đúng góc, **không rung** khi đứng yên, thời gian chuyển trạng thái **< 1 s**.
- [ ] Đóng cửa có hàng → tự khoá; đóng cửa không hàng → **không khoá**.
- [ ] Cảm biến bị rút dây/timeout → hệ thống báo lỗi và không khoá cửa.
- [ ] Chạy được trên laptop bằng Mock, `pytest tests/test_edge_hardware.py` pass.
- [ ] Person 3 gọi được các hàm theo đúng chữ ký ở mục 4 mà không cần sửa code của tôi.
- [ ] Có sơ đồ đấu dây và hướng dẫn hiệu chuẩn.

---

## 7. Câu hỏi cần thống nhất với nhóm

1. **Cảm biến đóng cửa:** có thêm reed switch/limit switch không? Nếu không, FSM sẽ dựa vào nút bấm hoặc timeout nào để biết shipper đã đóng cửa?
2. **Nhận diện khuôn mặt** (Person 1) sẽ gọi trực tiếp `unlock_door()` hay đi qua FSM + Server? _(đề xuất: qua FSM)_
3. Nếu tủ **trống sau khi shipper đóng cửa** thì xử lý thế nào: huỷ đơn, cho thử lại, hay cảnh báo qua Telegram?
4. Mất khả năng đối chiếu cân nặng nên cần Server (Person 4) bỏ bước kiểm tra weight; ai cập nhật `schemas.py` và API `confirm-deposit`?
5. Cơ chế **mở khoá khẩn cấp** (admin / chìa cơ) nếu servo hoặc điện hỏng?

---

## 8. Kế hoạch thực hiện (gợi ý)

| Giai đoạn | Công việc | Thời lượng |
|---|---|---|
| 1 | Chốt interface và schema với Person 3, Person 4 | 1–2 ngày |
| 2 | Viết driver + Mock cho siêu âm, test trên bàn | 2–3 ngày |
| 3 | Viết driver + Mock cho servo, thử cơ khí khoá | 2–3 ngày |
| 4 | Hiệu chuẩn cảm biến trong tủ thật, tinh chỉnh ngưỡng | 1–2 ngày |
| 5 | Tích hợp FSM, test end-to-end, sửa lỗi | 2–3 ngày |
| 6 | Viết tài liệu đấu dây, chuẩn bị demo | 1 ngày |

---

## 9. Danh sách linh kiện liên quan

| Linh kiện | Ghi chú |
|---|---|
| Cảm biến siêu âm HC-SR04 (hoặc JSN-SR04T) | Kèm cầu chia áp 1 kΩ / 2 kΩ cho chân ECHO |
| Servo SG90 / MG996R | Chọn theo lực khoá cần thiết |
| Nguồn 5 V ngoài (≥ 2 A nếu dùng MG996R) | Nối chung GND với Pi |
| Reed switch + nam châm (hoặc limit switch) | Phát hiện đóng cửa |
| Dây, breadboard / PCB, tụ lọc (470–1000 µF cho nguồn servo) | |
