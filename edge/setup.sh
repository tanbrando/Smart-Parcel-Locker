#!/usr/bin/env bash
# ==============================================================================
# Script cài đặt môi trường cho Raspberry Pi 4B - Smart Parcel Locker (Edge Node)
# Tác giả: Quốc (AI / Computer Vision & Edge)
# ==============================================================================

set -e

echo "=========================================================="
echo "🚀 Bắt đầu cài đặt môi trường Smart Parcel Locker trên Pi..."
echo "=========================================================="

# 1. Cập nhật hệ thống
echo "📦 [1/6] Cập nhật apt repositories..."
sudo apt update && sudo apt upgrade -y

# 2. Cài đặt các gói thư viện hệ thống (System Dependencies)
# - libzbar0, libzbar-dev: Đọc mã QR & Barcode (pyzbar)
# - python3-opencv, python3-picamera2: Camera CSI & xử lý hình ảnh
# - Các thư viện hỗ trợ OpenCV & hiển thị hình ảnh
echo "📦 [2/6] Cài đặt các gói thư viện hệ thống cần thiết..."
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
echo "🔧 [3/6] Cấu hình phần cứng (I2C & Camera)..."
sudo raspi-config nonint do_i2c 0 || true

# 4. Tạo môi trường ảo Python (Virtual Environment)
# Lưu ý: Cờ --system-site-packages bắt buộc để Python truy cập được picamera2 & libcamera của hệ thống Pi
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

echo "🐍 [4/6] Khởi tạo môi trường ảo Python tại $VENV_DIR..."
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv --system-site-packages "$VENV_DIR"
fi

# Kích hoạt venv
source "$VENV_DIR/bin/activate"

# 5. Cài đặt các thư viện Python
echo "📥 [5/6] Cài đặt các thư viện Python (Edge, Pyzbar, PaddleOCR)..."
pip install --upgrade pip

# Cài đặt requirements của Edge
pip install -r "$SCRIPT_DIR/requirements.txt"

# Cài đặt PaddlePaddle & PaddleOCR (dùng bản ARM64 CPU trên Pi)
pip install paddlepaddle paddleocr

# 6. Cấu hình biến môi trường và thư mục mô hình Offline
MODELS_DIR="$SCRIPT_DIR/models/paddlex"
echo "🧠 [6/6] Kiểm tra thư mục trọng số Offline: $MODELS_DIR"

if [ -d "$MODELS_DIR/official_models" ]; then
    echo "✅ Trọng số PaddleOCR đã có sẵn trong dự án! Pi sẽ chạy hoàn toàn Offline."
else
    echo "⚠️ Chưa tìm thấy weights trong $MODELS_DIR. Hệ thống sẽ tự tải về khi chạy lần đầu."
fi

# Tạo file kích hoạt nhanh môi trường .env_edge
cat << 'EOF' > "$SCRIPT_DIR/.env_edge"
# Thiết lập biến môi trường chạy trên Raspberry Pi
export CAMERA_MODE=raspberry
export USE_CSI_CAMERA=true
export MOCK_HARDWARE=false
export PADDLE_PDX_CACHE_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/models/paddlex"
export PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
export FLAGS_use_mkldnn=0
export FLAGS_enable_pir_api=0
EOF

echo ""
echo "=========================================================="
echo "🎉 CÀI ĐẶT HOÀN TẤT!"
echo "Để chạy thử nghiệm hệ thống tại tủ đồ, bạn chạy lệnh:"
echo ""
echo "  cd $SCRIPT_DIR"
echo "  source venv/bin/activate"
echo "  source .env_edge"
echo ""
echo "  # Chạy test ảnh:"
echo "  python test/test_camera_scanner.py --mode test"
echo ""
echo "  # Chạy thực tế bằng Camera CSI:"
echo "  python test/test_camera_scanner.py --mode raspberry"
echo "=========================================================="

