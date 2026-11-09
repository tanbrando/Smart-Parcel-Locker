#!/usr/bin/env bash
# ==============================================================================
# Script cài đặt môi trường cho Raspberry Pi 4B - Smart Parcel Locker (Edge Node)
# Tác giả: Quốc (AI / Computer Vision & Edge)
# ==============================================================================
# Logic: Môi trường ảo (venv) sẽ được tạo và dùng chung ngay tại thư mục gốc dự án:
#        Smart-Parcel-Locker/.venv
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Thiết lập đường dẫn venv cố định tại thư mục gốc dự án: Smart-Parcel-Locker/.venv
TARGET_VENV="$PROJECT_ROOT/.venv"

echo "=========================================================="
echo "🚀 Bắt đầu cài đặt môi trường Smart Parcel Locker trên Pi..."
echo "📂 Thư mục gốc dự án: $PROJECT_ROOT"
echo "📂 Thư mục Edge: $SCRIPT_DIR"
echo "🐍 Target venv: $TARGET_VENV"
echo "=========================================================="

# 1. Cập nhật danh sách gói phần mềm (apt update)
echo "📦 [1/5] Cập nhật danh sách gói phần mềm (apt update)..."
sudo apt update

# 2. Cài đặt các gói thư viện hệ thống (System Dependencies)
# - libzbar0, libzbar-dev: Đọc mã QR & Barcode (pyzbar)
# - python3-opencv, python3-picamera2: Camera CSI & xử lý hình ảnh
# - Các thư viện hỗ trợ OpenCV & hiển thị hình ảnh
echo "📦 [2/5] Cài đặt các gói thư viện hệ thống cần thiết..."
sudo apt install -y \
    python3-pip \
    python3-venv \
    python3-dev \
    libzbar0 \
    libzbar-dev \
    python3-opencv \
    python3-picamera2 \
    libatlas-base-dev \
    libopenjp2-7 \
    libtiff5 \
    libjpeg-dev \
    zlib1g-dev \
    i2c-tools \
    python3-smbus

# 3. Kích hoạt giao tiếp I2C và Camera nếu chưa bật
echo "🔧 [3/5] Cấu hình phần cứng (I2C)..."
sudo raspi-config nonint do_i2c 0 || true

# 4. Kiểm tra và tạo venv tại Smart-Parcel-Locker/.venv
echo "🐍 [4/5] Thiết lập môi trường ảo Python (.venv)..."
if [ -d "$TARGET_VENV" ] && [ -f "$TARGET_VENV/bin/activate" ]; then
    echo "✅ Đã tìm thấy .venv sẵn có tại: $TARGET_VENV"
else
    echo "⚙️ Đang khởi tạo môi trường ảo mới tại: $TARGET_VENV..."
    # Lưu ý: Cờ --system-site-packages bắt buộc để Python truy cập được picamera2 của hệ thống Pi
    python3 -m venv --system-site-packages "$TARGET_VENV"
    echo "✅ Đã tạo thành công .venv tại: $TARGET_VENV"
fi

# Kích hoạt venv
source "$TARGET_VENV/bin/activate"
echo "👉 Đang sử dụng Python: $(which python)"

# Đảm bảo pip của đúng target venv được sử dụng
if [[ "$(which python)" != "$TARGET_VENV"* ]]; then
    echo "❌ Lỗi: Chưa kích hoạt đúng venv tại $TARGET_VENV!"
    exit 1
fi

# 5. Cài đặt các thư viện từ requirements.txt của Edge
echo "📥 [5/5] Cài đặt các package từ edge/requirements.txt..."
pip install --upgrade pip
pip install -r "$SCRIPT_DIR/requirements.txt"

# 6. Cấu hình biến môi trường và thư mục mô hình Offline
MODELS_DIR="$SCRIPT_DIR/models/paddlex"
echo "🧠 Kiểm tra thư mục trọng số Offline: $MODELS_DIR"

if [ -d "$MODELS_DIR/official_models" ]; then
    echo "✅ Trọng số PaddleOCR đã có sẵn trong dự án! Pi sẽ chạy hoàn toàn Offline."
else
    echo "⚠️ Chưa tìm thấy weights trong $MODELS_DIR. Hệ thống sẽ tự tải về khi chạy lần đầu."
fi

# Tạo/cập nhật file kích hoạt nhanh môi trường .env_edge
cat << EOF > "$SCRIPT_DIR/.env_edge"
# Thiết lập biến môi trường chạy trên Raspberry Pi
export CAMERA_MODE=raspberry
export USE_CSI_CAMERA=true
export MOCK_HARDWARE=false
export PADDLE_PDX_CACHE_HOME="$MODELS_DIR"
export PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
export FLAGS_use_mkldnn=0
export FLAGS_enable_pir_api=0
EOF

echo ""
echo "=========================================================="
echo "🎉 CÀI ĐẶT HOÀN TẤT CHO PI!"
echo "Để chạy thử nghiệm hệ thống tại tủ đồ, bạn chạy lệnh:"
echo ""
echo "  source $TARGET_VENV/bin/activate"
echo "  source $SCRIPT_DIR/.env_edge"
echo ""
echo "  # Chạy test ảnh:"
echo "  python $SCRIPT_DIR/test/test_camera_scanner.py --mode test"
echo ""
echo "  # Chạy thực tế bằng Camera CSI:"
echo "  python $SCRIPT_DIR/test/test_camera_scanner.py --mode raspberry"
echo "=========================================================="
