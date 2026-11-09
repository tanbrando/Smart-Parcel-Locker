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

### 2. Edge / Raspberry Pi Setup
```bash
cd edge
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Run Edge Controller (automatically falls back to Mock Hardware if not on Raspberry Pi)
python main.py
```
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
