# 📦 Smart Parcel Locker (IoT Monorepo)

An automated, intelligent IoT Smart Parcel Locker system powered by **Raspberry Pi 4B**, Computer Vision, Load Cell sensor verification, and a Cloud-backed **FastAPI** server with Telegram notification integration.

---

## 👥 Team Roles & Responsibilities

| Role | Module | Primary Owner | Responsibilities |
|---|---|---|---|
| **Quốc** | `edge/cv/` | Computer Vision Engineer | Camera stream capture, QR/Barcode decoding (pyzbar), Waybill label OCR (PaddleOCR/Regex parsers). |
| **Việt** | `edge/hardware/` | Hardware & Embedded Driver Dev | Load Cell HX711 sensor (anti-fraud weight delta), Solenoid relay door triggers, LCD 1602 (I2C), and Buzzer. |
| **Nhật** | `edge/core/` | System & FSM Engineer | Finite State Machine orchestration, 4x4 Keypad rate-limiting / lockout, Edge API client, and `edge/main.py`. |
| **Tấn** | `server/` & `web/` | Full-stack & Cloud Architect | FastAPI server, SQLite/PostgreSQL ORM, Shopee screenshot OCR, OTP generator & rate limiter, Telegram Bot alerts, and Web Dashboard. |

---

## 📂 Project Structure

```text
smart-parcel-locker/
├── README.md                   # Project documentation & role division
├── docker-compose.yml          # Container orchestration for cloud backend
├── .gitignore
├── contracts/                  # Shared data schemas and mock fixtures
│   ├── __init__.py
│   ├── schemas.py              # Single source of truth (Pydantic / Dataclasses)
│   └── mock_data.py            # Reusable mock records for cross-module testing
├── edge/                       # Code deployed to Raspberry Pi 4B
│   ├── requirements.txt        # Edge dependencies (pyzbar, RPi.GPIO, opencv)
│   ├── config.py               # Pinout mapping, camera index, server endpoint
│   ├── main.py                 # Edge supervisor & FSM runtime
│   ├── cv/                     # [QUỐC]
│   │   ├── __init__.py
│   │   ├── scanner.py          # scan_package_label()
│   │   └── ocr_utils.py        # Tracking number & weight regex parsers
│   ├── hardware/               # [VIỆT]
│   │   ├── __init__.py
│   │   ├── hx711_loadcell.py   # measure_weight_delta()
│   │   ├── lock_controller.py  # open_locker_door()
│   │   └── indicators.py       # LCD 1602 & Buzzer feedback
│   └── core/                   # [NHẬT]
│       ├── __init__.py
│       ├── fsm.py              # State Machine (IDLE -> SCANNING -> UNLOCKED -> WEIGHING -> DONE)
│       ├── keypad.py           # 4x4 Keypad matrix with rate-limiting
│       └── api_client.py       # HTTP client calling Server endpoints
├── server/                     # [TẤN]
│   ├── requirements.txt        # Backend dependencies (FastAPI, uvicorn, SQLAlchemy)
│   ├── Dockerfile              # Docker image definition
│   ├── .env.example            # Environment variable template
│   ├── main.py                 # FastAPI app entry point
│   ├── core/
│   │   ├── config.py           # Configuration management
│   │   └── security.py         # OTP generation & verification
│   ├── db/
│   │   ├── session.py          # Database session & engine
│   │   └── models.py           # SQLAlchemy tables (User, Locker, Order, AccessLog)
│   ├── routers/
│   │   ├── orders.py           # Screenshot registration & query
│   │   ├── edge.py             # RPi verification, deposit confirmation, OTP check
│   │   └── lockers.py          # Locker admin & health monitoring
│   └── services/
│       ├── ocr_service.py      # Shopee screenshot order parsing
│       └── notifier.py         # Telegram bot notifications
├── web/                        # [TẤN] Minimal web dashboard
│   ├── index.html
│   └── README.md
└── tests/                      # Integration & Contract tests
    ├── test_edge_contracts.py  # Type contracts & mock validation
    └── test_server_api.py      # Backend API endpoints test suite
```

---

## 🚀 Quickstart Guide

### 1. Backend Server Setup
```bash
cd server
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env

# Run FastAPI server
uvicorn main:app --reload --port 8000
```
API Documentation will be available at: `http://localhost:8000/docs`

### 2. All-in-One Setup & Run on Raspberry Pi
See full wiring/pinout and per-component testing instructions in [`HARDWARE_GUIDE.md`](HARDWARE_GUIDE.md).
```bash
chmod +x setup.sh run_all.sh
./setup.sh

# Run FastAPI Server + Web Dashboard + Telegram Bot + Edge FSM together:
./run_all.sh         # Physical hardware mode
./run_all.sh --mock  # Interactive CLI mock mode
```

#### Face ID camera on phones (HTTPS)
Browsers only allow live camera access on HTTPS or `localhost`. To enroll Face ID with the live alignment HUD from a phone or another laptop on the LAN:
```bash
./run_all.sh --https               # HTTP :8000 (Edge) + HTTPS :8443 (self-signed cert in certs/)
./run_all.sh --server-only --https --https-port 9443
```
Open `https://<LAN_IP>:8443/portal` and accept the certificate warning once (iPhone Safari: *Show Details → visit this website*). The Edge controller keeps using `http://<host>:8000`.
Without HTTPS, the Face ID tab falls back to the phone's native camera to capture each of the 5 angles.

### 3. Run Tests
```bash
pytest tests/
```

---

## 🔄 Core Flow

```text
1. User uploads Shopee order screenshot on Web / App -> Server parses tracking & weight -> Order in PENDING.
2. Courier arrives -> CV Scanner reads waybill barcode/QR -> Edge sends verify-package to Server.
3. Server checks order -> Validates status -> Assigns available Locker -> Sends unlock signal.
4. Edge opens Locker Solenoid Relay -> Courier places parcel -> Edge measures weight delta via HX711.
5. Weight matches declared weight (+/- tolerance) -> Edge confirms deposit to Server.
6. Server marks Order DEPOSITED -> Generates 6-digit OTP -> Sends Telegram notification with OTP to Recipient.
7. Recipient arrives -> Inputs OTP via 4x4 Keypad -> Edge verifies OTP with Server -> Locker door pops open.
```

## Thử nghiệm xác minh khuôn mặt trên edge

### Nhận hàng bằng Face ID tại tủ

Đặt `FACE_YUNET` và `FACE_SFACE` thành đường dẫn tệp ONNX trên cả máy chủ
và Pi. Đặt cùng một khóa bí mật `FACE_DEVICE_KEY` trong môi trường máy chủ
và Pi. Dùng HTTPS với chứng chỉ được Pi tin cậy khi truyền ảnh và khóa qua mạng.

Đăng nhập `/portal`, chụp đủ năm tư thế và bấm **Lưu Face ID** để tạo hồ sơ
SFace theo tài khoản. Hồ sơ web từng lưu ảnh xem trước cần đăng ký lại.
Tại tủ, nhấn **D**, nhập mã tài khoản hiển thị trong mục Face ID, rồi nhấn
**#**. Làm theo năm hướng dẫn trên màn hình. Máy chủ chỉ cho mở một ngăn
chứa kiện của tài khoản khi cả năm ảnh khớp. Phím **#** từ màn hình chờ
vẫn mở luồng OTP.

### Demo độc lập bằng CLI

Công cụ edge bên dưới dùng hồ sơ SQLite chỉ định bằng `--db`.

Chạy từ thư mục gốc của repo với môi trường đã cài các thư viện edge. Tải
`face_detection_yunet_2023mar.onnx` và `face_recognition_sface_2021dec.onnx`
từ [YuNet](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet)
và [SFace](https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface).
Dùng webcam USB qua OpenCV và đặt cơ sở dữ liệu trong thư mục riêng ngoài repo.

```sh
python -m edge.cv.face_verify enroll user-123 --yunet /path/yunet.onnx --sface /path/sface.onnx --db /private/faces.sqlite3
python -m edge.cv.face_verify verify user-123 --yunet /path/yunet.onnx --sface /path/sface.onnx --db /private/faces.sqlite3
python -m edge.cv.face_verify adapt user-123 --yunet /path/yunet.onnx --sface /path/sface.onnx --db /private/faces.sqlite3
```

Trên máy có giao diện đồ họa, thêm `--preview` vào lệnh để xem webcam,
hướng dẫn và tiến độ từng góc. Cửa sổ cần bản `opencv-python` có hỗ trợ
HighGUI. Nếu môi trường dùng `opencv-python-headless`, hãy dùng môi trường
demo riêng với `opencv-python` để tránh trùng module `cv2`.
Nhấn Esc hoặc Q để hủy.

Lệnh đăng ký hướng dẫn nhìn thẳng, quay trái, quay phải, ngẩng nhẹ và cúi nhẹ. Mỗi góc cần ba
khung hình nhất quán. Chương trình sàng lọc theo số mặt, kích thước, độ sáng và
độ nét, sau đó lưu vector SFace. SQLite lưu vector dạng JSON và cần được bảo
vệ bằng quyền truy cập hệ điều hành. Lệnh xác minh so sánh 1:1 theo ID đã khai báo.
Chạy lại `enroll` với cùng ID để nâng cấp hồ sơ ba góc. Khi chạy `verify`,
mỗi bước chỉ lấy một ảnh đúng tư thế và chuyển tiếp sau khi ảnh khớp mẫu
cùng góc. Trên Pi dùng camera CSI, thêm `--picamera2` khi đăng ký hoặc xác minh.
Với ảnh chụp sẵn, thêm `--photos front.jpg left.jpg right.jpg up.jpg down.jpg`
vào lệnh `verify` và cung cấp ảnh theo đúng thứ tự đó.
Mã thoát 0 là đăng ký thành công hoặc khớp, 1 là không khớp, 2 là lỗi vận hành.

### Thích nghi mẫu

Lệnh `adapt` dành cho lượt thử do người vận hành kiểm soát. Mẫu mới phải khớp
mẫu đăng ký của cùng góc với cosine ít nhất 0,70. Vector thích nghi nhận 10%
trọng số từ mẫu mới và chỉ được lưu khi cosine với mẫu gốc vẫn đạt 0,90.
Xác minh dùng cả hai vector và luôn kiểm tra mức tương đồng tối thiểu với
mẫu gốc. Mẫu đăng ký được giữ để giới hạn trôi mẫu.

Đây là CLI thử nghiệm, độc lập với luồng nhận hàng OTP. Quay đầu được dùng
để thu tư thế. Triển khai tại tủ cần kiểm tra chống giả mạo, gắn đăng ký và cập nhật
mẫu với danh tính đã xác thực, và bảo vệ dữ liệu sinh trắc học.
Để đánh giá thích nghi, dùng các phiên riêng theo ngày và điều kiện ánh sáng.
So sánh tỷ lệ nhận nhầm, từ chối nhầm và thời gian xử lý với cùng ngưỡng, trước
và sau thích nghi. Ngưỡng trong mã là giá trị thử nghiệm. Tham khảo
[NIST SP 800-63B](https://pages.nist.gov/800-63-4/sp800-63b.html).
