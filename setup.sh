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
    git git-lfs curl openssl python3-pip python3-venv python3-dev
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

# 5b. Tự động tải 2 model Face ID (YuNet + SFace ONNX) từ OpenCV Zoo
FACE_MODELS_DIR="$EDGE_DIR/models/face"
YUNET_FILE="$FACE_MODELS_DIR/face_detection_yunet_2023mar.onnx"
SFACE_FILE="$FACE_MODELS_DIR/face_recognition_sface_2021dec.onnx"
YUNET_URL="https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
SFACE_URL="https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"

mkdir -p "$FACE_MODELS_DIR"
if [ ! -f "$YUNET_FILE" ] || [ "$(wc -c < "$YUNET_FILE")" -lt 100000 ]; then
    echo "📥 Đang tải model phát hiện khuôn mặt YuNet (~230KB)..."
    curl -fSL --retry 3 "$YUNET_URL" -o "$YUNET_FILE" || echo "⚠️ Không thể tải YuNet (kiểm tra mạng Internet)."
fi
if [ ! -f "$SFACE_FILE" ] || [ "$(wc -c < "$SFACE_FILE")" -lt 10000000 ]; then
    echo "📥 Đang tải model nhận diện khuôn mặt SFace (~38MB)..."
    curl -fSL --retry 3 "$SFACE_URL" -o "$SFACE_FILE" || echo "⚠️ Không thể tải SFace (kiểm tra mạng Internet)."
fi
if [ -f "$YUNET_FILE" ] && [ -f "$SFACE_FILE" ]; then
    echo "✅ Đã sẵn sàng 2 model Face ID (YuNet + SFace) tại: $FACE_MODELS_DIR"
fi

# 5c. Tự sinh & đồng bộ SECRET_KEY, FACE_DEVICE_KEY, FACE_YUNET, FACE_SFACE giữa server/.env và edge/.env
python - "$SERVER_DIR/.env" "$EDGE_DIR/.env" "$YUNET_FILE" "$SFACE_FILE" << 'PY'
import secrets
import sys
from pathlib import Path

server_env = Path(sys.argv[1])
edge_env = Path(sys.argv[2])
yunet_path = sys.argv[3]
sface_path = sys.argv[4]

def read_kv(path: Path):
    data = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        data[k.strip()] = v.strip()
    return data

def upsert_kv(path: Path, updates: dict):
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen = set()
    out = []
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k = s.split("=", 1)[0].strip()
            if k in updates:
                out.append(f"{k}={updates[k]}")
                seen.add(k)
                continue
        out.append(line)
    for k, v in updates.items():
        if k not in seen:
            out.append(f"{k}={v}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")

s_kv = read_kv(server_env)
e_kv = read_kv(edge_env)

# 1. SECRET_KEY
secret_key = s_kv.get("SECRET_KEY", "")
if not secret_key or "change-in-production" in secret_key:
    secret_key = secrets.token_hex(32)

# 2. FACE_DEVICE_KEY shared between server & edge
def valid_key(val: str) -> bool:
    return bool(val) and "change-me" not in val

face_key = s_kv.get("FACE_DEVICE_KEY", "")
if not valid_key(face_key):
    face_key = e_kv.get("FACE_DEVICE_KEY", "")
if not valid_key(face_key):
    face_key = secrets.token_hex(32)

upsert_kv(server_env, {
    "SECRET_KEY": secret_key,
    "FACE_DEVICE_KEY": face_key,
    "FACE_YUNET": yunet_path,
    "FACE_SFACE": sface_path,
})
upsert_kv(edge_env, {
    "FACE_DEVICE_KEY": face_key,
    "FACE_YUNET": yunet_path,
    "FACE_SFACE": sface_path,
})
print("✅ Đã tự động sinh & đồng bộ SECRET_KEY, FACE_DEVICE_KEY, FACE_YUNET, FACE_SFACE.")
PY

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

