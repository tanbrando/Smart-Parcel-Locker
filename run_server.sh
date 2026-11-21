#!/usr/bin/env bash
# ==============================================================================
# Smart Parcel Locker - Server Runner
# Khởi chạy độc lập FastAPI Server (Web Dashboard + Telegram Bot).
# ==============================================================================

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_VENV="$PROJECT_ROOT/.venv"

USE_RELOAD=false
HOST="0.0.0.0"
PORT="8000"
USE_HTTPS=false
HTTPS_PORT="8443"
CERT_DIR="$PROJECT_ROOT/certs"
CERT_FILE="$CERT_DIR/dev-cert.pem"
KEY_FILE="$CERT_DIR/dev-key.pem"

while [ $# -gt 0 ]; do
    case "$1" in
        --reload)
            USE_RELOAD=true
            shift
            ;;
        --port)
            PORT="${2:-8000}"
            shift 2
            ;;
        --https)
            USE_HTTPS=true
            shift
            ;;
        --https-port)
            HTTPS_PORT="${2:-8443}"
            shift 2
            ;;
        -h|--help)
            cat << 'EOF'
Cách dùng: bash run_server.sh [tùy chọn]

Tùy chọn:
  --port <num>        Cổng HTTP (mặc định: 8000)
  --https             Mở thêm cổng HTTPS (chứng chỉ tự ký) cho camera Face ID qua LAN
  --https-port <num>  Cổng HTTPS (mặc định: 8443)
  --reload            Bật uvicorn --reload (không dùng chung với --https)
  -h, --help          Hiển thị hướng dẫn này
EOF
            exit 0
            ;;
        *)
            echo "❌ Tham số không hợp lệ: $1 (dùng --help để xem hướng dẫn)"
            exit 1
            ;;
    esac
done

cd "$PROJECT_ROOT"

if [ ! -f "$TARGET_VENV/bin/activate" ]; then
    echo "❌ Không tìm thấy môi trường ảo tại: $TARGET_VENV"
    echo "👉 Vui lòng chạy lệnh cài đặt trước: ./setup.sh"
    exit 1
fi

# shellcheck disable=SC1091
source "$TARGET_VENV/bin/activate"
export PYTHONPATH="$PROJECT_ROOT"
export PYTHONUNBUFFERED=1

check_port_in_use() {
    python - "$1" << 'PY'
import socket, sys
port = int(sys.argv[1])
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(0.5)
in_use = s.connect_ex(("127.0.0.1", port)) == 0
s.close()
sys.exit(0 if in_use else 1)
PY
}

get_lan_ip() {
    local ip=""
    if command -v hostname >/dev/null 2>&1; then
        ip="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
    fi
    echo "${ip:-127.0.0.1}"
}

ensure_dev_cert() {
    local lan_ip="$1"
    if [ -f "$CERT_FILE" ] && [ -f "$KEY_FILE" ] \
        && openssl x509 -in "$CERT_FILE" -noout -text 2>/dev/null | grep -qE "IP Address:${lan_ip}(,|$)"; then
        return 0
    fi
    if ! command -v openssl >/dev/null 2>&1; then
        echo "❌ Cần cài openssl để dùng --https (sudo apt install openssl)."
        exit 1
    fi
    mkdir -p "$CERT_DIR"
    echo "🔐 Đang tạo chứng chỉ HTTPS tự ký cho ${lan_ip} ..."
    MSYS_NO_PATHCONV=1 openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days 825 \
        -subj "/CN=SmartLocker Dev" \
        -addext "subjectAltName=IP:${lan_ip},IP:127.0.0.1,DNS:localhost" \
        -addext "extendedKeyUsage=serverAuth" \
        -keyout "$KEY_FILE" -out "$CERT_FILE" >/dev/null 2>&1
}

if check_port_in_use "$PORT"; then
    echo "❌ Cổng $PORT đang bị tiến trình khác chiếm dụng!"
    echo "👉 Chạy: pkill -f 'server.main:app|server.serve' hoặc chọn --port khác."
    exit 1
fi

if [ "$USE_HTTPS" = true ] && check_port_in_use "$HTTPS_PORT"; then
    echo "❌ Cổng HTTPS $HTTPS_PORT đang bị chiếm dụng! Dùng --https-port để chọn cổng khác."
    exit 1
fi

LAN_IP="$(get_lan_ip)"

echo "=========================================================="
echo "🌐 SMART PARCEL LOCKER - SERVER LAUNCHER"
echo "📂 Project : $PROJECT_ROOT"
echo "=========================================================="

HAS_BOT_TOKEN="$(python -c "from server.core.config import settings; print('1' if settings.TELEGRAM_BOT_TOKEN else '0')" 2>/dev/null || echo '0')"
if [ "$HAS_BOT_TOKEN" = "0" ]; then
    echo "⚠️ Chưa cấu hình TELEGRAM_BOT_TOKEN trong server/.env - Bot Telegram sẽ tạm tắt."
else
    echo "✅ Đã phát hiện cấu hình TELEGRAM_BOT_TOKEN."
fi

echo "   • Web Dashboard : http://${LAN_IP}:${PORT}"
if [ "$USE_HTTPS" = true ]; then
    ensure_dev_cert "$LAN_IP"
    echo "   • HTTPS (camera): https://${LAN_IP}:${HTTPS_PORT}/portal"
    if [ "$USE_RELOAD" = true ]; then
        echo "⚠️ --reload không hỗ trợ cùng --https, bỏ qua --reload."
    fi
    exec python -u -m server.serve --host "$HOST" --port "$PORT" \
        --https-port "$HTTPS_PORT" --ssl-certfile "$CERT_FILE" --ssl-keyfile "$KEY_FILE"
else
    UVICORN_ARGS=(server.main:app --host "$HOST" --port "$PORT")
    if [ "$USE_RELOAD" = true ]; then
        UVICORN_ARGS+=(--reload)
    fi
    exec uvicorn "${UVICORN_ARGS[@]}"
fi
