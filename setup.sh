#!/usr/bin/env bash
# ==============================================================================
# Smart Parcel Locker - Unified Setup Script (Server + Edge on Raspberry Pi)
# Hỗ trợ Raspberry Pi OS Debian 12 (Bookworm) & Debian 13 (Trixie).
# Tối ưu tốc độ: bỏ qua `apt upgrade` mặc định và skip các gói đã cài sẵn.
# ==============================================================================

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EDGE_DIR="$PROJECT_ROOT/edge"
SERVER_DIR="$PROJECT_ROOT/server"
TARGET_VENV="$PROJECT_ROOT/.venv"
MARKER_FILE="$TARGET_VENV/.deps_installed.sha256"

DO_UPGRADE=false
FORCE_PIP=false

for arg in "$@"; do
    case "$arg" in
        --upgrade)
            DO_UPGRADE=true
            ;;
        --force)
            FORCE_PIP=true
            ;;
        -h|--help)
            cat << 'EOF'
Cách dùng: ./setup.sh [tùy chọn]

Tùy chọn:
  --upgrade   Chạy `sudo apt full-upgrade -y` (mặc định bỏ qua để tránh tốn 15-20 phút)
  --force     Ép cài đặt lại các thư viện Python dù requirements.txt không đổi
  -h, --help  Hiển thị hướng dẫn này
EOF
            exit 0
            ;;
        *)
            echo "⚠️ Tham số không hợp lệ: $arg (dùng --help để xem hướng dẫn)"
            exit 1
            ;;
    esac
done

echo "=========================================================="
echo "🚀 Cài đặt môi trường Smart Parcel Locker (Server + Edge)"
echo "📂 Thư mục gốc: $PROJECT_ROOT"
echo "🐍 Virtual env: $TARGET_VENV"
echo "=========================================================="

# ------------------------------------------------------------------------------
# 1. Kiểm tra & cài đặt các gói hệ thống (Tương thích Bookworm & Trixie)
# ------------------------------------------------------------------------------
echo "📦 [1/5] Kiểm tra các gói hệ thống (APT)..."

FIXED_PKGS=(
    git git-lfs curl python3-pip python3-venv python3-dev
    libzbar-dev python3-opencv
    libopenjp2-7 libjpeg-dev zlib1g-dev
    tesseract-ocr tesseract-ocr-vie
    i2c-tools python3-smbus
)

ALT_GROUPS=(
    "libzbar0t64 libzbar0"
    "libopenblas-dev libatlas-base-dev"
    "libtiff-dev libtiff6 libtiff5"
    "python3-rpi-lgpio python3-rpi.gpio"
)

IS_PI=false
if [ -f /proc/device-tree/model ] && grep -qi "raspberry" /proc/device-tree/model 2>/dev/null; then
    IS_PI=true
fi

MISSING_FIXED=()
for pkg in "${FIXED_PKGS[@]}"; do
    if ! dpkg -s "$pkg" >/dev/null 2>&1; then
        MISSING_FIXED+=("$pkg")
    fi
done

MISSING_GROUPS=()
for grp in "${ALT_GROUPS[@]}"; do
    found=false
    for cand in $grp; do
        if dpkg -s "$cand" >/dev/null 2>&1; then
            found=true
            break
        fi
    done
    if [ "$found" = false ]; then
        MISSING_GROUPS+=("$grp")
    fi
done

MISSING_PI_OPT=()
if [ "$IS_PI" = true ]; then
    for pkg in python3-picamera2; do
        if ! dpkg -s "$pkg" >/dev/null 2>&1; then
            MISSING_PI_OPT+=("$pkg")
        fi
    done
fi

if [ "$DO_UPGRADE" = true ] || [ ${#MISSING_FIXED[@]} -gt 0 ] || [ ${#MISSING_GROUPS[@]} -gt 0 ] || [ ${#MISSING_PI_OPT[@]} -gt 0 ]; then
    echo "🔄 Đang cập nhật danh sách gói (apt update)..."
    sudo apt update

    if [ "$DO_UPGRADE" = true ]; then
        echo "⬆️ Đang nâng cấp toàn bộ hệ thống (--upgrade)..."
        sudo apt full-upgrade -y
    fi

    TO_INSTALL=()
    for pkg in "${MISSING_FIXED[@]}"; do
        TO_INSTALL+=("$pkg")
    done

    for grp in "${MISSING_GROUPS[@]}"; do
        picked=""
        for cand in $grp; do
            if apt-cache show "$cand" 2>/dev/null | grep -q '^Package:'; then
                picked="$cand"
                break
            fi
        done
        if [ -n "$picked" ]; then
            TO_INSTALL+=("$picked")
        else
            echo "⚠️ Không tìm thấy gói phù hợp trong nhóm: $grp (bỏ qua)"
        fi
    done

    for pkg in "${MISSING_PI_OPT[@]}"; do
        if apt-cache show "$pkg" 2>/dev/null | grep -q '^Package:'; then
            TO_INSTALL+=("$pkg")
        fi
    done

    if [ ${#TO_INSTALL[@]} -gt 0 ]; then
        echo "📥 Cài đặt ${#TO_INSTALL[@]} gói hệ thống còn thiếu: ${TO_INSTALL[*]}"
        sudo apt install -y "${TO_INSTALL[@]}"
    fi
else
    echo "✅ Tất cả gói hệ thống đã có sẵn, bỏ qua bước apt update/install."
fi

# ------------------------------------------------------------------------------
# 2. Kích hoạt I2C trên Raspberry Pi
# ------------------------------------------------------------------------------
echo "🔧 [2/5] Kiểm tra cấu hình phần cứng I2C..."
if command -v raspi-config >/dev/null 2>&1; then
    sudo raspi-config nonint do_i2c 0 || true
    echo "✅ Đã kích hoạt giao tiếp I2C."
else
    echo "ℹ️ Không tìm thấy raspi-config (không phải Raspberry Pi OS), bỏ qua."
fi

# ------------------------------------------------------------------------------
# 3. Khởi tạo Virtual Environment (.venv) dùng chung tại gốc dự án
# ------------------------------------------------------------------------------
echo "🐍 [3/5] Thiết lập môi trường ảo Python (.venv)..."
if [ -d "$TARGET_VENV" ] && [ -f "$TARGET_VENV/bin/activate" ]; then
    echo "✅ Đã tìm thấy .venv sẵn có tại: $TARGET_VENV"
else
    echo "⚙️ Đang tạo .venv với --system-site-packages..."
    python3 -m venv --system-site-packages "$TARGET_VENV"
    echo "✅ Đã tạo thành công .venv."
fi

# shellcheck disable=SC1091
source "$TARGET_VENV/bin/activate"
echo "👉 Python đang dùng: $(which python)"

# ------------------------------------------------------------------------------
# 4. Cài đặt thư viện Python (Server + Edge) với cache hash
# ------------------------------------------------------------------------------
echo "📥 [4/5] Kiểm tra & cài đặt thư viện Python (Server + Edge)..."

if command -v sha256sum >/dev/null 2>&1; then
    CURRENT_HASH="$(cat "$SERVER_DIR/requirements.txt" "$EDGE_DIR/requirements.txt" | sha256sum | awk '{print $1}')"
else
    CURRENT_HASH="$(cat "$SERVER_DIR/requirements.txt" "$EDGE_DIR/requirements.txt" | shasum -a 256 | awk '{print $1}')"
fi

NEED_PIP=true
if [ "$FORCE_PIP" = false ] && [ -f "$MARKER_FILE" ]; then
    SAVED_HASH="$(cat "$MARKER_FILE" 2>/dev/null || true)"
    if [ "$SAVED_HASH" = "$CURRENT_HASH" ] && python -c "import fastapi, uvicorn, pydantic, cv2, pyzbar, smbus2, dotenv, pytesseract" >/dev/null 2>&1; then
        NEED_PIP=false
    fi
fi

if [ "$NEED_PIP" = true ]; then
    python -m pip install --upgrade pip
    pip install --upgrade-strategy only-if-needed -r "$SERVER_DIR/requirements.txt" -r "$EDGE_DIR/requirements.txt"
    if [ "$IS_PI" = true ] && ! python -c "import RPi.GPIO" >/dev/null 2>&1; then
        echo "⚙️ Cài bổ sung rpi-lgpio vào .venv cho GPIO..."
        pip install rpi-lgpio || pip install RPi.GPIO || true
    fi
    echo "$CURRENT_HASH" > "$MARKER_FILE"
    echo "✅ Đã cài đặt xong toàn bộ thư viện Server & Edge."
else
    echo "✅ Các thư viện Python đã đầy đủ & khớp requirements.txt (dùng --force để cài lại)."
fi

# ------------------------------------------------------------------------------
# 5. Tự động tạo file .env (nếu chưa có) & kiểm tra OCR model offline
# ------------------------------------------------------------------------------
echo "⚙️ [5/5] Thiết lập file cấu hình (.env)..."

if [ ! -f "$EDGE_DIR/.env" ] && [ -f "$EDGE_DIR/.env.example" ]; then
    cp "$EDGE_DIR/.env.example" "$EDGE_DIR/.env"
    sed -i 's|^SERVER_API_URL=.*|SERVER_API_URL=http://127.0.0.1:8000|' "$EDGE_DIR/.env"
    echo "✅ Đã tạo $EDGE_DIR/.env (trỏ về Server localhost http://127.0.0.1:8000)."
else
    echo "ℹ️ Giữ nguyên cấu hình $EDGE_DIR/.env hiện tại."
fi

if [ ! -f "$SERVER_DIR/.env" ] && [ -f "$SERVER_DIR/.env.example" ]; then
    cp "$SERVER_DIR/.env.example" "$SERVER_DIR/.env"
    echo "✅ Đã tạo $SERVER_DIR/.env (hãy điền TELEGRAM_BOT_TOKEN nếu cần Telegram Bot)."
else
    echo "ℹ️ Giữ nguyên cấu hình $SERVER_DIR/.env hiện tại."
fi

MODELS_DIR="$EDGE_DIR/models/paddlex"
SAMPLE_PARAM="$MODELS_DIR/official_models/PP-OCRv5_mobile_det/inference.pdiparams"
if [ -f "$SAMPLE_PARAM" ] && [ "$(wc -c < "$SAMPLE_PARAM")" -lt 1024 ] && command -v git-lfs >/dev/null 2>&1; then
    echo "📥 Phát hiện file trọng số Git LFS dạng pointer, đang tải qua git lfs pull..."
    (cd "$PROJECT_ROOT" && git lfs install >/dev/null 2>&1 && git lfs pull) || true
fi
if [ -d "$MODELS_DIR/official_models" ]; then
    echo "✅ Trọng số OCR đã sẵn sàng tại: $MODELS_DIR (hỗ trợ Tesseract + fallback)"
else
    echo "ℹ️ Đã cấu hình Tesseract OCR làm engine mặc định trên Pi."
fi

chmod +x "$PROJECT_ROOT/setup.sh" 2>/dev/null || true
chmod +x "$PROJECT_ROOT/run_all.sh" 2>/dev/null || true

echo ""
echo "=========================================================="
echo "🎉 CÀI ĐẶT HOÀN TẤT!"
echo "👉 Để chạy toàn bộ hệ thống (Server + Web + Bot + Edge), chạy:"
echo ""
echo "     ./run_all.sh"
echo ""
echo "   Hoặc chạy ở chế độ giả lập CLI không cần cắm phần cứng:"
echo ""
echo "     ./run_all.sh --mock"
echo "=========================================================="

