#!/usr/bin/env bash
# ==============================================================================
# Smart Parcel Locker - Edge Runner
# Khởi chạy độc lập Edge Controller (Servo, Siêu âm, LCD, Buzzer, Keypad, Camera).
# ==============================================================================

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_VENV="$PROJECT_ROOT/.venv"

USE_MOCK=false
CUSTOM_SERVER_URL=""

while [ $# -gt 0 ]; do
    case "$1" in
        --mock)
            USE_MOCK=true
            shift
            ;;
        --server)
            CUSTOM_SERVER_URL="${2:-}"
            shift 2
            ;;
        -h|--help)
            cat << 'EOF'
Cách dùng: bash run_edge.sh [tùy chọn]

Tùy chọn:
  --mock            Chạy chế độ giả lập CLI (MOCK_HARDWARE=true, CAMERA_MODE=test)
  --server <url>    Chỉ định URL của Server (mặc định đọc từ edge/.env hoặc http://127.0.0.1:8000)
  -h, --help        Hiển thị hướng dẫn này
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

# Nạp cấu hình Edge từ edge/.env nếu có
if [ -f "$PROJECT_ROOT/edge/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_ROOT/edge/.env"
    set +a
fi

if [ -n "$CUSTOM_SERVER_URL" ]; then
    export SERVER_API_URL="$CUSTOM_SERVER_URL"
elif [ -z "${SERVER_API_URL:-}" ]; then
    export SERVER_API_URL="http://127.0.0.1:8000"
fi

if [ "$USE_MOCK" = true ]; then
    export MOCK_HARDWARE=true
    export CAMERA_MODE=test
fi

echo "=========================================================="
echo "🤖 SMART PARCEL LOCKER - EDGE LAUNCHER"
echo "📂 Project : $PROJECT_ROOT"
echo "🌐 Server  : $SERVER_API_URL"
echo "⚙️ Mock    : $USE_MOCK"
echo "=========================================================="

exec python -u "$PROJECT_ROOT/edge/main.py"
