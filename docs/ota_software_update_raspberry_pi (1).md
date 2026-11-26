# Thiết kế chức năng OTA Software Update cho dự án IoT

## 1. Mục tiêu

Xây dựng chức năng **OTA (Over-The-Air) Software Update** cho phép Admin cập nhật toàn bộ phần mềm ứng dụng đang chạy trên Raspberry Pi (**backend Python và frontend**) thông qua Admin Dashboard.

Admin build bản mới trên máy của mình, đóng gói thành một file ZIP, upload lên Dashboard và yêu cầu cập nhật. Raspberry Pi tự nhận lệnh, tải gói phần mềm, xác minh, triển khai phiên bản mới, khởi động lại ứng dụng, kiểm tra hoạt động và báo cáo kết quả. Nếu thất bại, Pi tự quay về phiên bản trước.

**Phạm vi phiên bản đầu tiên:**

- Cập nhật **backend (Python)** và **frontend (file tĩnh đã build)**, cả hai chạy trên Raspberry Pi.
- Admin upload file ZIP trực tiếp lên Dashboard.
- Frontend được **build trên máy Admin**, không build trên Pi.
- Không cập nhật Raspberry Pi OS, kernel hoặc firmware.
- Không cập nhật chính OTA Agent (xem mục 13: Hạn chế đã biết).
- Không yêu cầu SSH hay copy file thủ công trong quy trình cập nhật thông thường.

## 2. Kiến trúc tổng thể

```text
+-----------------------+
|    Admin Dashboard    |
| Upload ZIP / Releases |
| Select device / Update|
+-----------+-----------+
            |
            | HTTPS REST API
            v
+-----------------------+
|      Backend API      |
| Django / FastAPI      |
| Auth / Version / Jobs |
| Ký số release         |
+----+-------------+----+
     |             |
     |             +----------------------+
     |                                    |
     v                                    v
+----------------+              +-------------------+
| PostgreSQL     |              | Package Storage   |
| Devices        |              | ZIP + Metadata    |
| Releases       |              | Local / S3 / MinIO|
| Update Jobs    |              +-------------------+
+----------------+
     |
     | MQTT: update command / status
     v
+-----------------------+
|     MQTT Broker       |
+-----------+-----------+
            |
            v
+--------------------------------------------+
| Raspberry Pi                               |
|                                            |
|  Python OTA Agent                          |
|   1. Nhận lệnh                             |
|   2. Tải ZIP                               |
|   3. Xác minh SHA-256 + chữ ký             |
|   4. Giải nén an toàn vào releases/<ver>   |
|   5. Tạo venv, cài dependency              |
|   6. Đổi symlink current (atomic)          |
|   7. Restart service, reload nginx         |
|   8. Health check, rollback nếu lỗi        |
|   9. Báo kết quả                           |
|                                            |
|  Ứng dụng được cập nhật:                   |
|   nginx --> frontend (file tĩnh)           |
|   nginx --> /api --> backend Python        |
+--------------------------------------------+
```

### Thành phần

| Thành phần | Trách nhiệm |
|---|---|
| Admin Dashboard | Upload ZIP, tạo release, chọn thiết bị, theo dõi tiến trình |
| Backend API (OTA) | Xác thực Admin, quản lý release, ký số, tạo và theo dõi update job |
| PostgreSQL | Lưu thiết bị, phiên bản, lịch sử cập nhật |
| Package Storage | Lưu các gói ZIP đã phát hành |
| MQTT Broker | Gửi lệnh cập nhật và nhận trạng thái thiết bị |
| Python OTA Agent | Tải, xác minh, triển khai và rollback phần mềm trên Pi |
| systemd | Quản lý vòng đời backend và OTA Agent |
| nginx | Phục vụ frontend tĩnh và reverse proxy `/api` sang backend |

ThingsBoard có thể tiếp tục dùng để giám sát telemetry, trạng thái online/offline và dashboard IoT. Phần quản lý file release nên do Backend OTA đảm nhiệm; MQTT có thể dùng chung hạ tầng nếu thiết kế quyền truy cập và topic phù hợp.

## 3. Quy trình cập nhật

1. Admin build frontend (`npm run build`) và đóng gói backend + frontend thành ZIP.
2. Admin đăng nhập Dashboard, upload ZIP, nhập version và changelog.
3. Backend kiểm tra file, tạo release, tính SHA-256 và **ký số** release.
4. Admin chọn một hoặc nhiều Raspberry Pi và nhấn Update.
5. Backend tạo update job rồi gửi MQTT command đến thiết bị.
6. OTA Agent nhận lệnh, tải ZIP qua HTTPS (link có hạn hoặc token theo thiết bị).
7. Agent kiểm tra SHA-256, chữ ký số và cấu trúc package.
8. Agent giải nén an toàn vào `releases/<version>/` (thư mục chưa được `current` trỏ tới).
9. Agent tạo virtualenv và cài dependency cho release mới. Nếu lỗi: hủy update, bản đang chạy không bị ảnh hưởng.
10. Agent chuyển symlink `current` sang release mới bằng thao tác atomic, restart backend, reload nginx.
11. Agent thực hiện health check (gọi `/health`, kiểm tra đúng version).
12. Thành công: báo `SUCCESS`. Thất bại: chuyển symlink về bản cũ, restart và báo `ROLLED_BACK`.
13. Dashboard hiển thị trạng thái và nhật ký cập nhật.

## 4. Định dạng gói ZIP

```text
release-v1.1.0.zip
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── requirements.txt
│   └── ...
├── frontend/              <- kết quả build (index.html, assets/...)
│   ├── index.html
│   └── assets/
├── manifest.json
└── CHANGELOG.md
```

Ví dụ `manifest.json`:

```json
{
  "app_name": "iot-device-app",
  "version": "1.1.0",
  "min_agent_version": "1.0.0",
  "components": {
    "backend": {
      "path": "backend",
      "entrypoint": "main.py",
      "requirements": "requirements.txt",
      "python_version": "3.11",
      "restart_service": "iot-app.service"
    },
    "frontend": {
      "path": "frontend",
      "reload_service": "nginx"
    }
  },
  "health_check": {
    "url": "http://127.0.0.1:8000/health",
    "timeout_seconds": 60,
    "expect_version": "1.1.0"
  },
  "db_migration": false
}
```

Manifest là metadata mô tả package. Backend OTA vẫn lưu SHA-256 và chữ ký của file ZIP; Agent phải xác minh trước khi giải nén.

**Lưu ý:** Không đưa mật khẩu, token MQTT, API key, private key hoặc file `.env` vào ZIP. Bí mật lưu riêng trên thiết bị (`/etc/iot-app/`).

## 5. Cấu trúc thư mục trên Raspberry Pi

```text
/opt/iot-app/                      <- code, chỉ Agent được ghi
├── releases/
│   ├── 1.0.0/
│   │   ├── backend/
│   │   ├── frontend/
│   │   └── venv/                  <- virtualenv riêng cho release
│   └── 1.1.0/
├── current -> releases/1.1.0      <- symlink
└── downloads/                     <- file ZIP tạm

/etc/iot-app/                      <- config và secret, KHÔNG nằm trong release
├── config.yaml
└── secrets.env

/var/lib/iot-app/                  <- dữ liệu ứng dụng (database, uploads...)

/var/lib/iot-ota/
└── state.json                     <- trạng thái job đang chạy (phục hồi khi mất điện)

/opt/iot-ota/                      <- OTA Agent, nằm ngoài releases/
├── ota_agent.py
└── config.yaml
```

**Nguyên tắc:**

- `current` là symlink trỏ tới phiên bản đang chạy. Backend, frontend và venv luôn khớp version vì cùng nằm trong một release; rollback quay lại cả ba.
- **Dữ liệu và config nằm ngoài `releases/`**, nếu không sẽ mất khi đổi version hoặc dọn release cũ.
- Virtualenv chứa đường dẫn tuyệt đối, vì vậy **tạo venv ngay tại đường dẫn cuối cùng** `releases/<version>/venv`, không tạo ở nơi khác rồi di chuyển.
- Giữ lại 2-3 release gần nhất, xóa các bản cũ hơn để tránh đầy thẻ SD.
- Agent và backend chạy bằng user riêng, quyền tối thiểu; không chạy bằng root.

## 6. Cấu hình nginx và systemd

### nginx

```nginx
server {
    listen 80;

    # Frontend: luôn trỏ qua symlink current
    root /opt/iot-app/current/frontend;
    index index.html;

    location / {
        try_files $uri /index.html;   # SPA routing
    }

    # index.html không cache, file có hash trong tên thì cache lâu
    location = /index.html {
        add_header Cache-Control "no-cache";
    }
    location /assets/ {
        add_header Cache-Control "public, max-age=31536000, immutable";
    }

    # Backend
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
    }
}
```

Frontend là file tĩnh nên không cần restart khi cập nhật. Sau khi đổi symlink chỉ cần `nginx -s reload` (hoặc `systemctl reload nginx`) để chắc chắn nginx dùng đường dẫn mới. Nên dùng bundler tạo tên file có hash (Vite, webpack) để trình duyệt không giữ cache bản cũ.

### systemd (backend)

```ini
[Unit]
Description=IoT App Backend
After=network.target

[Service]
User=iot-app
WorkingDirectory=/opt/iot-app/current/backend
EnvironmentFile=/etc/iot-app/secrets.env
ExecStart=/opt/iot-app/current/venv/bin/python main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

### Quyền cho OTA Agent

Agent chạy bằng user riêng (ví dụ `iot-ota`), chỉ được chạy đúng các lệnh cần thiết qua sudoers:

```text
iot-ota ALL=(root) NOPASSWD: /bin/systemctl restart iot-app.service, /bin/systemctl reload nginx
```

## 7. Thiết kế MQTT

Topic theo từng thiết bị:

```text
devices/{device_id}/ota/command
devices/{device_id}/ota/status
```

Lệnh từ Backend đến thiết bị:

```json
{
  "job_id": "job-2026-001",
  "action": "UPDATE",
  "version": "1.1.0",
  "download_url": "https://server.example.com/releases/1.1.0.zip?token=...",
  "sha256": "EXPECTED_SHA256_HASH",
  "signature": "BASE64_ED25519_SIGNATURE"
}
```

Trạng thái từ thiết bị về Backend:

```json
{
  "job_id": "job-2026-001",
  "device_id": "pi-001",
  "version": "1.1.0",
  "status": "DOWNLOADING",
  "progress": 35,
  "message": "Downloading software package"
}
```

| Trạng thái | Ý nghĩa |
|---|---|
| PENDING | Đang chờ thiết bị nhận lệnh |
| DOWNLOADING | Đang tải package |
| VERIFYING | Đang xác minh hash, chữ ký và cấu trúc |
| INSTALLING | Đang giải nén, cài dependency |
| RESTARTING | Đang chuyển version và restart service |
| HEALTH_CHECK | Đang kiểm tra hoạt động |
| SUCCESS | Cập nhật thành công |
| FAILED | Cập nhật thất bại (bản cũ vẫn chạy) |
| ROLLED_BACK | Đã khôi phục phiên bản trước |
| DEVICE_OFFLINE | Thiết bị không kết nối |

### Độ tin cậy của lệnh

- **Idempotent**: mỗi lệnh có `job_id` duy nhất; nhận lại cùng `job_id` thì không cài lặp.
- **Thiết bị offline**: dùng MQTT **QoS 1 + persistent session** (`clean_session=false`). Ngoài ra, mỗi khi Agent kết nối lại, nó hỏi Backend "có job nào đang chờ cho tôi không" để không bỏ sót lệnh.
- **Timeout**: job quá hạn mà thiết bị chưa phản hồi thì chuyển `DEVICE_OFFLINE`/`FAILED`.
- **Bảo mật**: TLS cho MQTT, xác thực riêng từng thiết bị, ACL để thiết bị chỉ đọc `command` và ghi `status` của chính nó.

## 8. Thiết kế Backend API

| Method | Endpoint | Mục đích |
|---|---|---|
| POST | `/api/releases/` | Upload ZIP và tạo release |
| GET | `/api/releases/` | Danh sách release |
| GET | `/api/releases/{id}/` | Chi tiết release |
| POST | `/api/update-jobs/` | Tạo yêu cầu cập nhật |
| GET | `/api/update-jobs/{id}/` | Xem trạng thái job |
| GET | `/api/devices/` | Danh sách thiết bị |
| GET | `/api/devices/{id}/updates/` | Lịch sử cập nhật của thiết bị |
| POST | `/api/devices/{id}/rollback/` | Yêu cầu rollback |
| GET | `/api/devices/{id}/pending-job/` | Agent hỏi job đang chờ khi kết nối lại |

Các endpoint cần xác thực và phân quyền. Chỉ Admin được phát hành release hoặc tạo update job. Thiết bị chỉ đọc lệnh dành cho chính nó và cập nhật trạng thái của chính nó. Link tải ZIP dùng **presigned URL có thời hạn** hoặc token theo thiết bị, không để công khai.

## 9. Thiết kế cơ sở dữ liệu

### Bảng `devices`

| Trường | Kiểu gợi ý | Mô tả |
|---|---|---|
| id | UUID | ID thiết bị |
| device_code | VARCHAR | Mã thiết bị duy nhất |
| name | VARCHAR | Tên hiển thị |
| current_version | VARCHAR | Version đang chạy |
| status | VARCHAR | Online / Offline |
| last_seen | TIMESTAMP | Lần cuối thiết bị kết nối |

### Bảng `software_releases`

| Trường | Kiểu gợi ý | Mô tả |
|---|---|---|
| id | UUID | ID release |
| version | VARCHAR | Version phần mềm |
| file_path | TEXT | Vị trí lưu ZIP |
| sha256 | CHAR(64) | Hash của ZIP |
| signature | TEXT | Chữ ký số Ed25519 |
| changelog | TEXT | Nội dung thay đổi |
| created_by | UUID | Admin phát hành |
| created_at | TIMESTAMP | Thời điểm phát hành |

### Bảng `update_jobs`

| Trường | Kiểu gợi ý | Mô tả |
|---|---|---|
| id | UUID | ID job |
| device_id | UUID | Thiết bị được cập nhật |
| release_id | UUID | Release đích |
| status | VARCHAR | Trạng thái cập nhật |
| progress | INTEGER | Tiến trình 0-100 |
| message | TEXT | Thông báo gần nhất |
| started_at | TIMESTAMP | Thời điểm bắt đầu |
| completed_at | TIMESTAMP | Thời điểm kết thúc |

Nên có thêm bảng `update_job_logs` để lưu từng sự kiện trong một job, và bảng `audit_logs` để ghi mọi hành động của Admin.

## 10. Quy trình an toàn và rollback

### Triển khai an toàn

1. Tải ZIP vào `downloads/`, giới hạn dung lượng tối đa.
2. Kiểm tra **SHA-256** và **chữ ký số Ed25519** (Backend giữ private key, Pi giữ public key).
3. Kiểm tra `manifest.json`: đúng `app_name`, version hợp lệ, `min_agent_version` phù hợp, **không downgrade** ngoài ý muốn.
4. Giải nén an toàn:
   - Từ chối đường dẫn tuyệt đối và đường dẫn chứa `..` (path traversal).
   - Từ chối symlink bên trong ZIP.
   - Giới hạn tổng dung lượng và số file sau giải nén (chống zip bomb).
5. Giải nén vào `releases/<version>/` (chưa được `current` trỏ tới nên bản đang chạy không bị ảnh hưởng).
6. Tạo `releases/<version>/venv` và `pip install -r requirements.txt`. Nếu lỗi: xóa thư mục release dở dang, báo `FAILED`, bản cũ vẫn chạy bình thường.
7. Chuyển symlink `current` bằng thao tác atomic:
   ```bash
   ln -sfn /opt/iot-app/releases/1.1.0 /opt/iot-app/current.tmp
   mv -T /opt/iot-app/current.tmp /opt/iot-app/current
   ```
8. Restart backend, reload nginx.
9. Health check.

### Health check

Không dùng `systemctl is-active` làm tiêu chí duy nhất vì service có thể "active" nhưng ứng dụng đã lỗi. Agent nên:

- Gọi `GET /health` của backend, **retry trong 30-60 giây**.
- Kiểm tra response trả về đúng `version` mong đợi.
- Kiểm tra frontend trả về `index.html` (HTTP 200) qua nginx.

Nếu thất bại: đổi symlink về release cũ, restart lại, xác nhận bản cũ chạy được, rồi báo `ROLLED_BACK`.

### Mất điện hoặc gián đoạn giữa chừng

Agent ghi trạng thái job xuống `/var/lib/iot-ota/state.json` ở mỗi bước (ví dụ: đã tải xong, đã đổi symlink, đang health check). Khi Agent khởi động lại và thấy job chưa hoàn tất, nó quyết định tiếp tục hoặc rollback dựa trên bước cuối cùng đã ghi, rồi báo kết quả về Backend.

### Database migration

Rollback code không tự rollback database. Nếu release mới đổi schema:

- Thiết kế migration **tương thích ngược** (thêm cột, không xóa/đổi tên ngay), để bản cũ vẫn chạy được trên schema mới.
- Đặt `"db_migration": true` trong manifest để Dashboard cảnh báo Admin trước khi phát hành.
- Chạy migration sau khi health check bản mới thành công, hoặc backup database trước khi migrate.

### Bảo mật bổ sung

- HTTPS cho tải package, TLS cho MQTT.
- Xác thực riêng từng thiết bị; không dùng chung credential cho toàn bộ fleet.
- SHA-256 chỉ đảm bảo toàn vẹn; **chữ ký số** mới chứng minh nguồn phát hành. Nếu kẻ tấn công kiểm soát được server cập nhật mà không có chữ ký, họ chạy được code tùy ý trên mọi Pi.
- Ghi audit log cho mọi hành động Admin.
- Giới hạn số thiết bị cập nhật đồng thời và triển khai theo đợt (staged rollout).

## 11. Kế hoạch triển khai theo giai đoạn

### Giai đoạn 1: OTA cơ bản cho một Raspberry Pi

- Cài nginx, backend, OTA Agent bằng systemd; bố trí thư mục như mục 5.
- Backend OTA: upload ZIP, lưu release, tính SHA-256.
- Agent nhận lệnh, tải ZIP, kiểm tra hash, giải nén an toàn.
- Tạo venv, đổi symlink, restart backend, reload nginx.
- Health check và rollback tự động.
- Báo kết quả về Backend.

### Giai đoạn 2: Quản lý nhiều thiết bị

- Đăng ký và xác thực từng Raspberry Pi.
- Tạo update job cho nhiều thiết bị.
- Hiển thị trạng thái online/offline và tiến trình.
- Lưu lịch sử cập nhật theo thiết bị.
- Xử lý thiết bị offline (persistent session + hỏi pending job).

### Giai đoạn 3: Độ tin cậy và bảo mật

- Chữ ký số Ed25519 (có thể làm sớm từ giai đoạn 1 vì khá đơn giản).
- Phục hồi sau mất điện bằng `state.json`.
- Triển khai theo nhóm thiết bị và giới hạn concurrency.
- Kiểm thử các tình huống: package lỗi, sai hash, sai chữ ký, `pip install` lỗi, hết dung lượng, service không khởi động được, health check thất bại, mất điện giữa lúc cập nhật.

## 12. Phạm vi demo phù hợp cho đồ án

Bắt đầu với **một Raspberry Pi**, chạy cả backend và frontend:

1. Chạy ứng dụng `1.0.0` (nginx + backend) trên Pi.
2. Sửa code backend và giao diện frontend, build thành `1.1.0`, đóng ZIP.
3. Admin upload ZIP trên Dashboard.
4. Admin nhấn Update.
5. Pi tự tải và triển khai; refresh trình duyệt thấy giao diện mới, API trả version mới.
6. Dashboard hiển thị `SUCCESS` và version `1.1.0`.
7. Tạo bản `1.2.0` cố tình lỗi (ví dụ `/health` trả lỗi) để demo **rollback tự động** về `1.1.0`.
8. Thử một ZIP sai hash hoặc sai chữ ký để demo từ chối cài đặt.

Khi demo một thiết bị ổn định, mới mở rộng sang nhiều Raspberry Pi.

## 13. Hạn chế đã biết

- **OTA Agent không tự cập nhật** được chính nó vì nằm ngoài `releases/`. Với đồ án chấp nhận; hướng mở rộng là tách Agent thành một release riêng với cơ chế cập nhật có hai Agent luân phiên.
- Không cập nhật OS, kernel, firmware, và không cập nhật các gói hệ thống (apt).
- Rollback chỉ khôi phục code; thay đổi dữ liệu/schema cần được xử lý riêng (mục 10).
- Cần Pi có đủ dung lượng thẻ SD để giữ nhiều release và venv.

## 14. Kết luận

Giải pháp đề xuất là **Custom OTA System sử dụng Python OTA Agent + Django/FastAPI Backend + MQTT + PostgreSQL**, cập nhật đồng thời backend và frontend chạy trên Raspberry Pi.

Admin Dashboard quản lý release và yêu cầu cập nhật; Backend phân phối package đã ký và điều phối job; Raspberry Pi chủ động nhận lệnh, xác minh, triển khai và tự rollback khi lỗi. Nhờ cấu trúc `releases/` + symlink `current`, backend, frontend và môi trường Python luôn đồng bộ và có thể quay lui cùng nhau.

ThingsBoard tiếp tục đảm nhiệm giám sát IoT và có thể hiển thị thêm trạng thái cập nhật. Thiết kế này loại bỏ thao tác SSH và copy code thủ công trong quy trình cập nhật thông thường, đồng thời tạo nền tảng để mở rộng thành hệ thống quản lý phần mềm cho nhiều thiết bị IoT.
