#!/usr/bin/env bash
# ==============================================================================
# Script cài đặt môi trường cho Raspberry Pi 4B - Smart Parcel Locker (Edge Node)
# Tác giả: Quốc (AI / Computer Vision & Edge)
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ==============================================================================
# 🔧 CẤU HÌNH ĐƯỜNG DẪN VENV (BẠN TỰ ĐIỀN ĐƯỜNG DẪN CỦA MÌNH VÀO ĐÂY)
# ==============================================================================
# - Nếu bạn có venv sẵn trên Pi, hãy điền đường dẫn tuyệt đối hoặc tương đối vào đây:
#   Ví dụ: CUSTOM_VENV_PATH="/home/pi/my_env" hoặc CUSTOM_VENV_PATH="$HOME/venv"
# - Nếu để trống (""), script sẽ mặc định tìm hoặc tạo venv tại: "$SCRIPT_DIR/venv"
CUSTOM_VENV_PATH="~/IOT/.venv"

# Mở rộng dấu ngã (~) thành $HOME nếu người dùng đặt dấu ~ trong chuỗi ngoặc kép
CUSTOM_VENV_PATH="${CUSTOM_VENV_PATH/#\~/$HOME}"

# Xác định đường dẫn venv mục tiêu
TARGET_VENV="${CUSTOM_VENV_PATH:-$SCRIPT_DIR/venv}"

echo "=========================================================="
echo "🚀 Bắt đầu cài đặt môi trường Smart Parcel Locker trên Pi..."
echo "📂 Thư mục mã nguồn: $SCRIPT_DIR"
echo "🐍 Target venv: $TARGET_VENV"
echo "=========================================================="

# 1. Cập nhật danh sách gói phần mềm (apt update)
# Lưu ý: Bỏ qua 'apt upgrade' để tránh mất thời gian cập nhật toàn bộ hệ điều hành
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

# 4. Kiểm tra venv theo cấu hình; nếu không tìm thấy thì tự động tạo mới
echo "🐍 [4/5] Thiết lập môi trường ảo Python (venv)..."
if [ -d "$TARGET_VENV" ] && [ -f "$TARGET_VENV/bin/activate" ]; then
    echo "✅ Đã tìm thấy venv có sẵn tại: $TARGET_VENV"
else
    echo "⚠️ Không tìm thấy venv tại '$TARGET_VENV'. Tiến hành tạo venv mới..."
    # Lưu ý: Cờ --system-site-packages bắt buộc để Python truy cập được picamera2 của hệ thống Pi
    python3 -m venv --system-site-packages "$TARGET_VENV"
    echo "✅ Đã tạo mới venv tại: $TARGET_VENV"
fi

# Kích hoạt venv
source "$TARGET_VENV/bin/activate"
echo "👉 Đang sử dụng Python: $(which python)"

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
