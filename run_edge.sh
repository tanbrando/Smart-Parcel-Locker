#!/usr/bin/env bash
# ==============================================================================
# Smart Parcel Locker - Edge Runner
# Khởi chạy độc lập Edge Controller (Servo, Siêu âm, LCD, Buzzer, Keypad, Camera).
# ==============================================================================

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_VENV="$PROJECT_ROOT/.venv"

USE_MOCK=false
USE_DISPLAY=false
CUSTOM_SERVER_URL=""

while [ $# -gt 0 ]; do
    case "$1" in
        --mock)
            USE_MOCK=true
            shift
            ;;
        --display|--preview)
            USE_DISPLAY=true
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
  --mock              Chạy chế độ giả lập CLI (MOCK_HARDWARE=true, CAMERA_MODE=test)
  --display           Hiện cửa sổ Camera trực tiếp (Quét mã & Face ID) qua MobaXterm X11
  --preview           Alias của --display
  --server <url>      Chỉ định URL của Server (mặc định đọc từ edge/.env hoặc http://127.0.0.1:8000)
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

if [ "$USE_DISPLAY" = true ]; then
    export CAMERA_PREVIEW=true
    if [ -z "${DISPLAY:-}" ]; then
        echo "⚠️ Đã bật --display nhưng chưa thấy biến DISPLAY (X11 Forwarding)."
        echo "👉 Trên MobaXterm: bật X server (góc trên phải) + tích 'X11-Forwarding' trong SSH Session."
        echo "👉 Trên Pi: sudo apt install -y xauth && đảm bảo 'X11Forwarding yes' trong /etc/ssh/sshd_config."
    fi
    HAS_CV_GUI="$(python -c "import cv2; print('1' if getattr(cv2, 'currentUIFramework', lambda: '')() else '0')" 2>/dev/null || echo '0')"
    if [ "$HAS_CV_GUI" = "0" ]; then
        echo "⚠️ OpenCV trong .venv hiện là bản headless (chưa hỗ trợ cv2.imshow)."
        echo "👉 Chạy 1 lần lệnh sau trên Pi để dùng python3-opencv có GUI của hệ thống:"
        echo "     pip uninstall -y opencv-python-headless"
    fi
fi

echo "=========================================================="
echo "🤖 SMART PARCEL LOCKER - EDGE LAUNCHER"
echo "📂 Project : $PROJECT_ROOT"
echo "🌐 Server  : $SERVER_API_URL"
echo "⚙️ Mock    : $USE_MOCK"
echo "🖥️ Display : $USE_DISPLAY (DISPLAY=${DISPLAY:-none})"
echo "=========================================================="

exec python -u "$PROJECT_ROOT/edge/main.py"
