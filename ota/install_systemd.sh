#!/usr/bin/env bash
# ==============================================================================
# Cài đặt cấu trúc thư mục OTA + 3 systemd service trên Raspberry Pi 4B:
#   1. smart-locker-server.service  (FastAPI + Web Dashboard + Telegram Bot)
#   2. smart-locker-edge.service    (Edge Hardware Controller)
#   3. smart-locker-ota.service     (OTA Agent chạy độc lập ngoài releases/)
# ==============================================================================
set -euo pipefail

APP_USER="${SUDO_USER:-$USER}"
SRC_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OTA_BASE="/opt/smart-locker"
OTA_AGENT_DIR="/opt/smart-locker-ota"
INIT_VER="$(cat "$SRC_REPO/VERSION" 2>/dev/null | tr -d '[:space:]' || echo '1.0.0')"

echo "🚀 Thiết lập OTA trên Raspberry Pi cho user: $APP_USER (version: $INIT_VER)"

sudo mkdir -p "$OTA_BASE/releases/$INIT_VER" "$OTA_BASE/downloads" "$OTA_BASE/shared/server" "$OTA_BASE/shared/edge" "$OTA_BASE/shared/ota_storage" "$OTA_BASE/shared/certs" "$OTA_AGENT_DIR"
sudo chown -R "$APP_USER:$APP_USER" "$OTA_BASE" "$OTA_AGENT_DIR"

# 1. Copy mã nguồn ban đầu vào releases/<INIT_VER> và trỏ symlink current
rsync -a --exclude='.venv' --exclude='.git' --exclude='__pycache__' "$SRC_REPO/" "$OTA_BASE/releases/$INIT_VER/"
ln -sfn "$OTA_BASE/releases/$INIT_VER" "$OTA_BASE/current"

# 2. Giữ nguyên .venv dùng chung (tránh cài lại OpenCV/PaddleOCR mất 20 phút mỗi lần OTA)
if [ -d "$SRC_REPO/.venv" ] && [ ! -e "$OTA_BASE/.venv" ]; then
    ln -sfn "$SRC_REPO/.venv" "$OTA_BASE/.venv"
fi

# 3. Copy file cấu hình & DB sang shared/
[ -f "$SRC_REPO/server/.env" ] && cp -n "$SRC_REPO/server/.env" "$OTA_BASE/shared/server/.env" || true
[ -f "$SRC_REPO/edge/.env" ] && cp -n "$SRC_REPO/edge/.env" "$OTA_BASE/shared/edge/.env" || true
[ -f "$SRC_REPO/parcel_locker.db" ] && cp -n "$SRC_REPO/parcel_locker.db" "$OTA_BASE/shared/parcel_locker.db" || true

# 4. Copy OTA Agent ra thư mục riêng độc lập ngoài releases/
cp "$SRC_REPO/ota/agent.py" "$OTA_AGENT_DIR/agent.py"

# 5. Tạo 3 systemd services
sudo tee /etc/systemd/system/smart-locker-server.service >/dev/null <<EOF
[Unit]
Description=Smart Parcel Locker FastAPI Server
After=network-online.target

[Service]
User=$APP_USER
WorkingDirectory=$OTA_BASE/current
Environment=PYTHONPATH=$OTA_BASE/current
Environment=PYTHONUNBUFFERED=1
ExecStart=$OTA_BASE/.venv/bin/uvicorn server.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/smart-locker-edge.service >/dev/null <<EOF
[Unit]
Description=Smart Parcel Locker Edge Controller
After=smart-locker-server.service

[Service]
User=$APP_USER
WorkingDirectory=$OTA_BASE/current
Environment=PYTHONPATH=$OTA_BASE/current
Environment=PYTHONUNBUFFERED=1
Environment=SERVER_API_URL=http://127.0.0.1:8000
ExecStart=$OTA_BASE/.venv/bin/python -u $OTA_BASE/current/edge/main.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/smart-locker-ota.service >/dev/null <<EOF
[Unit]
Description=Smart Parcel Locker Independent OTA Agent
After=network-online.target

[Service]
User=$APP_USER
WorkingDirectory=$OTA_AGENT_DIR
Environment=PYTHONPATH=$OTA_BASE/current
Environment=PYTHONUNBUFFERED=1
Environment=OTA_BASE_DIR=$OTA_BASE
Environment=OTA_SERVER_URL=http://127.0.0.1:8000
ExecStart=$OTA_BASE/.venv/bin/python -u $OTA_AGENT_DIR/agent.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 6. Cấp quyền sudoers tối thiểu cho OTA Agent restart đúng 2 service
echo "$APP_USER ALL=(root) NOPASSWD: /bin/systemctl restart smart-locker-server.service, /bin/systemctl restart smart-locker-edge.service" | sudo tee /etc/sudoers.d/smart-locker-ota >/dev/null
sudo chmod 0440 /etc/sudoers.d/smart-locker-ota

sudo systemctl daemon-reload
sudo systemctl enable --now smart-locker-server.service smart-locker-edge.service smart-locker-ota.service

echo "✅ Hoàn tất cài đặt OTA systemd services!"
echo "   Kiểm tra log OTA Agent: journalctl -u smart-locker-ota.service -f"
