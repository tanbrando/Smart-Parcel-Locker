#!/usr/bin/env bash
# ==============================================================================
# Smart Parcel Locker - All-in-One Runner Script
# Khởi chạy đồng bộ FastAPI Server (Web Dashboard + Telegram Bot) và Edge Node.
# ==============================================================================

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_VENV="$PROJECT_ROOT/.venv"
LOG_DIR="$PROJECT_ROOT/logs"
SERVER_LOG="$LOG_DIR/server.log"

MODE="full"         # full | server | edge
USE_MOCK=false
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
        --mock)
            USE_MOCK=true
            shift
            ;;
        --server-only)
            MODE="server"
            shift
            ;;
        --edge-only)
            MODE="edge"
            shift
            ;;
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
Cách dùng: ./run_all.sh [tùy chọn]

Tùy chọn:
  (mặc định)     Chạy Full: FastAPI Server (nền) + Edge Controller (foreground)
  --mock         Chạy ở chế độ giả lập CLI (MOCK_HARDWARE=true, CAMERA_MODE=test)
  --server-only  Chỉ chạy FastAPI Server + Web Dashboard + Telegram Bot
  --edge-only    Chỉ chạy Edge Controller (khi Server đặt ở máy khác)
  --reload       Bật uvicorn --reload (dành cho phát triển code Server)
  --port <num>   Chỉ định cổng Server (mặc định: 8000)
  --https        Mở thêm cổng HTTPS (chứng chỉ tự ký) để điện thoại/laptop
                 dùng camera Face ID qua mạng LAN. Edge vẫn dùng HTTP.
  --https-port <num>  Cổng HTTPS (mặc định: 8443)
  -h, --help     Hiển thị hướng dẫn này
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

# Nạp cấu hình Server từ server/.env và Edge từ edge/.env (đồng bộ FACE_DEVICE_KEY, FACE_YUNET, FACE_SFACE)
if [ -f "$PROJECT_ROOT/server/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_ROOT/server/.env"
    set +a
fi
if [ -f "$PROJECT_ROOT/edge/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_ROOT/edge/.env"
    set +a
fi

# Mặc định trỏ tới thư mục model Face ID cục bộ nếu chưa cấu hình
export FACE_YUNET="${FACE_YUNET:-$PROJECT_ROOT/edge/models/face/face_detection_yunet_2023mar.onnx}"
export FACE_SFACE="${FACE_SFACE:-$PROJECT_ROOT/edge/models/face/face_recognition_sface_2021dec.onnx}"

# Nếu người dùng bật --mock thì ép chế độ giả lập đè lên .env
if [ "$USE_MOCK" = true ]; then
    export MOCK_HARDWARE=true
    export CAMERA_MODE=test
fi

SERVER_PID=""
CLEANUP_DONE=false

cleanup() {
    if [ "$CLEANUP_DONE" = true ]; then
        return
    fi
    CLEANUP_DONE=true

    if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
        echo ""
        echo "🛑 Đang tắt FastAPI Server (PID: $SERVER_PID)..."
        kill -TERM "$SERVER_PID" 2>/dev/null || true
        for _ in $(seq 1 10); do
            if ! kill -0 "$SERVER_PID" 2>/dev/null; then
                break
            fi
            sleep 0.5
        done
        if kill -0 "$SERVER_PID" 2>/dev/null; then
            echo "⚠️ Ép dừng tiến trình Server còn sót..."
            kill -KILL "$SERVER_PID" 2>/dev/null || true
        fi
        echo "✅ Đã tắt Server sạch sẽ."
    fi
}
trap cleanup EXIT INT TERM

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

wait_for_server_health() {
    local url="http://127.0.0.1:${1}/health"
    local max_wait=30
    for i in $(seq 1 "$max_wait"); do
        if [ -n "$SERVER_PID" ] && ! kill -0 "$SERVER_PID" 2>/dev/null; then
            echo "❌ FastAPI Server bị dừng đột ngột khi khởi động! Log gần nhất:"
            tail -n 30 "$SERVER_LOG" || true
            return 1
        fi
        if python - "$url" << 'PY' >/dev/null 2>&1
import sys, urllib.request
with urllib.request.urlopen(sys.argv[1], timeout=1.0) as resp:
    sys.exit(0 if resp.status == 200 else 1)
PY
        then
            return 0
        fi
        sleep 1
    done
    echo "❌ Hết thời gian chờ (${max_wait}s) nhưng Server chưa phản hồi tại $url. Kiểm tra $SERVER_LOG:"
    tail -n 30 "$SERVER_LOG" || true
    return 1
}

get_lan_ip() {
    local ip=""
    if command -v hostname >/dev/null 2>&1; then
        ip="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
    fi
    echo "${ip:-127.0.0.1}"
}

echo "=========================================================="
echo "🚀 SMART PARCEL LOCKER - SYSTEM LAUNCHER"
echo "📂 Project : $PROJECT_ROOT"
echo "⚙️ Mode    : $MODE (Mock Edge: $USE_MOCK)"
echo "=========================================================="

# Kiểm tra cấu hình Telegram Bot nếu có chạy Server
if [ "$MODE" = "full" ] || [ "$MODE" = "server" ]; then
    HAS_BOT_TOKEN="$(python -c "from server.core.config import settings; print('1' if settings.TELEGRAM_BOT_TOKEN else '0')" 2>/dev/null || echo '0')"
    if [ "$HAS_BOT_TOKEN" = "0" ]; then
        echo "⚠️ Chưa cấu hình TELEGRAM_BOT_TOKEN trong server/.env (hoặc .env) - Bot Telegram sẽ tạm tắt."
    else
        echo "✅ Đã phát hiện cấu hình TELEGRAM_BOT_TOKEN."
    fi
fi

# Kiểm tra trạng thái Model & Key cho Face ID
if [ -f "$FACE_YUNET" ] && [ -f "$FACE_SFACE" ] && [ -n "${FACE_DEVICE_KEY:-}" ]; then
    echo "✅ Face ID sẵn sàng (YuNet + SFace ONNX + FACE_DEVICE_KEY)."
else
    echo "⚠️ Thiếu model Face ID hoặc FACE_DEVICE_KEY — hãy chạy ./setup.sh để tự động tải model & sinh key."
fi

# Sinh chứng chỉ tự ký (SAN gồm IP LAN + localhost) cho chế độ --https.
# iOS yêu cầu chứng chỉ có subjectAltName, hạn <= 825 ngày và EKU serverAuth.
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

LAN_IP="$(get_lan_ip)"

# Lệnh khởi chạy Server: uvicorn thường, hoặc launcher HTTP + HTTPS khi bật --https
if [ "$USE_HTTPS" = true ]; then
    ensure_dev_cert "$LAN_IP"
    if [ "$USE_RELOAD" = true ]; then
        echo "⚠️ --reload không hỗ trợ cùng --https, bỏ qua --reload."
    fi
    SERVER_CMD=(python -m server.serve --host "$HOST" --port "$PORT"
        --https-port "$HTTPS_PORT" --ssl-certfile "$CERT_FILE" --ssl-keyfile "$KEY_FILE")
else
    SERVER_CMD=(uvicorn server.main:app --host "$HOST" --port "$PORT")
    if [ "$USE_RELOAD" = true ]; then
        SERVER_CMD+=(--reload)
    fi
fi

print_server_urls() {
    echo "   • Web Dashboard : http://${LAN_IP}:${PORT}"
    if [ "$USE_HTTPS" = true ]; then
        echo "   • HTTPS (camera): https://${LAN_IP}:${HTTPS_PORT}/portal  (chấp nhận cảnh báo chứng chỉ lần đầu)"
    fi
}

check_ports_free() {
    if check_port_in_use "$PORT"; then
        echo "❌ Cổng $PORT đang bị tiến trình khác chiếm dụng!"
        echo "👉 Nếu Server cũ chưa tắt, hãy chạy: pkill -f 'server.main:app|server.serve' hoặc chọn --port khác."
        exit 1
    fi
    if [ "$USE_HTTPS" = true ] && check_port_in_use "$HTTPS_PORT"; then
        echo "❌ Cổng HTTPS $HTTPS_PORT đang bị chiếm dụng! Dùng --https-port để chọn cổng khác."
        exit 1
    fi
}

# 1. Khởi chạy FastAPI Server
if [ "$MODE" = "server" ]; then
    check_ports_free
    echo "🌐 Khởi chạy FastAPI Server..."
    print_server_urls
    "${SERVER_CMD[@]}"
    exit 0
fi

if [ "$MODE" = "full" ]; then
    mkdir -p "$LOG_DIR"
    check_ports_free

    echo "🌐 Đang khởi chạy FastAPI Server chạy nền (log: logs/server.log)..."
    "${SERVER_CMD[@]}" >"$SERVER_LOG" 2>&1 &
    SERVER_PID=$!

    echo "⏳ Đang chờ Server sẵn sàng..."
    wait_for_server_health "$PORT"

    echo "✅ Server đã ONLINE (PID: $SERVER_PID)"
    print_server_urls
    echo "   • Local Health  : http://127.0.0.1:${PORT}/health"
    echo "   • Server Logs   : tail -f logs/server.log"
    echo "----------------------------------------------------------"
fi

# 2. Khởi chạy Edge Controller ở foreground (bấm Ctrl+C để dừng sạch cả hệ thống)
if [ "$MODE" = "full" ] || [ "$MODE" = "edge" ]; then
    # Ở chế độ full, Edge luôn kết nối trực tiếp tới Server local vừa khởi chạy
    if [ "$MODE" = "full" ]; then
        export SERVER_API_URL="http://127.0.0.1:${PORT}"
    fi
    echo "🤖 Đang khởi chạy Edge Controller (nhấn Ctrl+C để dừng toàn bộ hệ thống)..."
    set +e
    python "$PROJECT_ROOT/edge/main.py"
    EDGE_EXIT=$?
    set -e
    exit "$EDGE_EXIT"
fi
