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

# Nạp cấu hình Edge từ edge/.env nếu có
if [ -f "$PROJECT_ROOT/edge/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_ROOT/edge/.env"
    set +a
fi

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

# 1. Khởi chạy FastAPI Server
if [ "$MODE" = "server" ]; then
    if check_port_in_use "$PORT"; then
        echo "❌ Cổng $PORT đang bị tiến trình khác chiếm dụng! Hãy tắt tiến trình cũ trước."
        exit 1
    fi
    UVICORN_ARGS=(server.main:app --host "$HOST" --port "$PORT")
    if [ "$USE_RELOAD" = true ]; then
        UVICORN_ARGS+=(--reload)
    fi
    echo "🌐 Khởi chạy FastAPI Server tại http://$(get_lan_ip):${PORT} ..."
    uvicorn "${UVICORN_ARGS[@]}"
    exit 0
fi

if [ "$MODE" = "full" ]; then
    mkdir -p "$LOG_DIR"
    if check_port_in_use "$PORT"; then
        echo "❌ Cổng $PORT đang bị tiến trình khác chiếm dụng!"
        echo "👉 Nếu Server cũ chưa tắt, hãy chạy: pkill -f 'uvicorn server.main:app' hoặc chọn --port khác."
        exit 1
    fi

    UVICORN_ARGS=(server.main:app --host "$HOST" --port "$PORT")
    if [ "$USE_RELOAD" = true ]; then
        UVICORN_ARGS+=(--reload)
    fi

    echo "🌐 Đang khởi chạy FastAPI Server chạy nền (log: logs/server.log)..."
    uvicorn "${UVICORN_ARGS[@]}" >"$SERVER_LOG" 2>&1 &
    SERVER_PID=$!

    echo "⏳ Đang chờ Server sẵn sàng..."
    wait_for_server_health "$PORT"

    LAN_IP="$(get_lan_ip)"
    echo "✅ Server đã ONLINE (PID: $SERVER_PID)"
    echo "   • Web Dashboard : http://${LAN_IP}:${PORT}"
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
