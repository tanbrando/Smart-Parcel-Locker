"""
Centralized Telegram Markdown Message Templates [Person 4].
All bot message formatting and notifications are consolidated here for consistency and branding.
"""
from typing import List, Optional
from datetime import datetime


class TelegramTemplates:
    """Consolidated message templates for both Outgoing Alerts and Interactive Commands."""

    # -------------------------------------------------------------------------
    # Outgoing Notifications (Triggered by Edge Pi / System Events)
    # -------------------------------------------------------------------------
    @staticmethod
    def parcel_deposited(
        tracking_number: str,
        locker_number: int,
        delta_weight: int,
        otp_code: str,
        valid_hours: int,
    ) -> str:
        return (
            f"📦 *BƯU KIỆN ĐÃ ĐẾN SMART PARCEL LOCKER!*\n\n"
            f"• *Mã vận đơn:* `{tracking_number}`\n"
            f"• *Ngăn tủ:* *Số {locker_number}*\n"
            f"• *Khối lượng thực tế:* `{delta_weight}g`\n"
            f"• *Mã OTP lấy hàng:* `{otp_code}`\n"
            f"• *Thời hạn hiệu lực:* {valid_hours} giờ\n\n"
            f"👉 Vui lòng đến tủ thông minh, nhập mã OTP `{otp_code}` trên bàn phím để mở ngăn số {locker_number}."
        )

    @staticmethod
    def parcel_collected(tracking_number: str, locker_number: int) -> str:
        return (
            f"✅ *NHẬN HÀNG THÀNH CÔNG!*\n\n"
            f"Bưu kiện `{tracking_number}` tại ngăn tủ số *{locker_number}* đã được lấy đi an toàn.\n"
            f"Cảm ơn bạn đã sử dụng Smart Parcel Locker!"
        )

    # -------------------------------------------------------------------------
    # Interactive Bot Commands (Account Linking & Rebinding Guards)
    # -------------------------------------------------------------------------
    @staticmethod
    def activation_success(user_id: int, full_name: str, phone: str) -> str:
        return (
            f"✅ *KÍCH HOẠT TÀI KHOẢN THÀNH CÔNG!*\n\n"
            f"• *Mã User:* `#{user_id}`\n"
            f"• *Khách hàng:* *{full_name}*\n"
            f"• *Số điện thoại:* `{phone}`\n\n"
            f"👉 Giờ đây bạn có thể gửi trực tiếp ảnh chụp màn hình đơn hàng vào khung chat này để lưu đơn!\n"
            f"Gõ `/help` để xem danh sách các câu lệnh tiện ích."
        )

    @staticmethod
    def rebinding_conflict_device_already_linked(linked_user_id: int, linked_user_name: str) -> str:
        return (
            f"⚠️ Thiết bị Telegram này hiện đang liên kết với tài khoản #{linked_user_id} "
            f"({linked_user_name}). Vui lòng gõ lệnh /unlink tài khoản cũ trước khi liên kết với tài khoản mới."
        )

    @staticmethod
    def rebinding_conflict_account_already_taken() -> str:
        return "❌ Tài khoản này đã được liên kết với một Telegram khác. Vui lòng liên hệ Admin để gỡ liên kết trước."

    @staticmethod
    def user_not_found(user_id: int) -> str:
        return f"❌ Không tìm thấy User ID #{user_id}. Vui lòng liên hệ Admin để được cấp tài khoản trên Web."

    @staticmethod
    def unlink_success(user_id: int, user_name: str) -> str:
        return f"✅ Đã gỡ liên kết thiết bị khỏi tài khoản #{user_id} ({user_name}) thành công."

    @staticmethod
    def unlink_unlinked_device() -> str:
        return "ℹ️ Thiết bị Telegram này hiện chưa liên kết với tài khoản nào."

    # -------------------------------------------------------------------------
    # Welcome & Start Messages
    # -------------------------------------------------------------------------
    @staticmethod
    def start_already_linked(user_name: str, user_id: int) -> str:
        return (
            f"👋 Xin chào *{user_name}* (ID #{user_id})!\n"
            f"Tài khoản của bạn đã được kích hoạt. Bạn có thể gửi ảnh đơn hàng bất kỳ lúc nào.\n"
            f"Gõ `/help` để xem các lệnh hỗ trợ."
        )

    @staticmethod
    def start_unlinked_prompt() -> str:
        return (
            "👋 Chào mừng bạn đến với *Smart Parcel Locker*!\n\n"
            "❌ Tài khoản của bạn chưa được Quản trị viên cấp phép.\n"
            "Vui lòng liên hệ Admin để được tạo tài khoản trên Web và nhận mã User ID kích hoạt (ví dụ: `/link 3`)."
        )

    # -------------------------------------------------------------------------
    # Order Status & Locker Inquiries
    # -------------------------------------------------------------------------
    @staticmethod
    def unactivated_prompt() -> str:
        return "❌ Bạn chưa kích hoạt tài khoản. Vui lòng liên hệ Admin để nhận User ID và nhập `/link <user_id>`."

    @staticmethod
    def no_orders() -> str:
        return "📭 Bạn chưa có đơn hàng nào trên hệ thống. Hãy gửi ảnh chụp đơn hàng vào đây để đăng ký!"

    @staticmethod
    def orders_summary(
        full_name: str,
        stored_orders: list,
        pending_orders: list,
        collected_orders: list,
    ) -> str:
        lines = [f"📋 *DANH SÁCH ĐƠN HÀNG CỦA {full_name.upper()}*\n"]

        if stored_orders:
            lines.append("📥 *ĐƠN HÀNG ĐANG TRONG TỦ (HÃY ĐI LẤY):*")
            for o in stored_orders:
                locker_num = o.locker.locker_number if o.locker else 1
                lines.append(
                    f"• Mã: `{o.tracking_number}` | Ngăn tủ: *#{locker_num}*\n"
                    f"  👉 *MÃ OTP:* `{o.otp_code}` (KL: {o.actual_weight}g)"
                )
            lines.append("")

        if pending_orders:
            lines.append("⏳ *ĐƠN HÀNG ĐANG CHỜ SHIPPER GIAO:*")
            for o in pending_orders:
                lines.append(f"• Mã: `{o.tracking_number}` | Đơn: `{o.order_code or '-'}` (Dự kiến: {o.expected_weight}g)")
            lines.append("")

        if collected_orders:
            lines.append("✅ *ĐƠN HÀNG ĐÃ NHẬN GẦN ĐÂY:*")
            for o in collected_orders[:3]:
                lines.append(f"• Mã: `{o.tracking_number}` (Đã lấy thành công)")

        return "\n".join(lines)

    @staticmethod
    def order_detail(
        tracking_number: str,
        order_code: Optional[str],
        status_value: str,
        locker_info: str,
        otp_info: str,
        expected_weight: int,
        actual_weight: Optional[int],
        created_at_str: str,
    ) -> str:
        return (
            f"📦 *CHI TIẾT BƯU KIỆN:* `{tracking_number}`\n\n"
            f"• *Mã đơn hàng:* `{order_code or '-'}`\n"
            f"• *Trạng thái:* *{status_value}*\n"
            f"• *Vị trí:* {locker_info}\n"
            f"• *Mã OTP lấy hàng:* {otp_info}\n"
            f"• *Khối lượng dự kiến:* `{expected_weight}g`\n"
            f"• *Khối lượng thực tế:* `{actual_weight or '-'}g`\n"
            f"• *Thời gian tạo:* {created_at_str}"
        )

    @staticmethod
    def order_not_found(code: str) -> str:
        return f"🔍 Không tìm thấy đơn hàng nào có mã `{code}` thuộc tài khoản của bạn."

    @staticmethod
    def lockers_summary(empty_count: int, total: int, locker_lines: List[str]) -> str:
        lines = [
            f"🔐 *TÌNH TRẠNG TỦ THÔNG MINH:*\n",
            f"• Hiện có *{empty_count}/{total}* ngăn đang trống, sẵn sàng nhận bưu kiện.",
        ]
        lines.extend(locker_lines)
        return "\n".join(lines)

    @staticmethod
    def user_profile(user_id: int, full_name: str, phone: str, phone_last4: str, chat_id: int) -> str:
        return (
            f"👤 *THÔNG TIN TÀI KHOẢN:*\n\n"
            f"• *User ID:* `#{user_id}`\n"
            f"• *Họ và tên:* *{full_name}*\n"
            f"• *Số điện thoại:* `{phone}` (Đuôi: {phone_last4})\n"
            f"• *Telegram Chat ID:* `{chat_id}`\n\n"
            f"Gõ `/unlink` nếu bạn muốn hủy liên kết tài khoản khỏi thiết bị này."
        )

    # -------------------------------------------------------------------------
    # Photo Ingestion Responses
    # -------------------------------------------------------------------------
    @staticmethod
    def photo_upload_unlinked() -> str:
        return (
            "❌ Bạn chưa kích hoạt tài khoản trên Smart Parcel Locker!\n\n"
            "Vui lòng liên hệ Quản trị viên (Admin) để được tạo tài khoản trên Web và nhận mã User ID. "
            "Sau đó gõ `/link <user_id>` để kích hoạt."
        )

    @staticmethod
    def order_registered_success(
        tracking_number: str,
        order_code: Optional[str],
        full_name: str,
        expected_weight: int,
    ) -> str:
        return (
            f"📦 *ĐÃ TIẾP NHẬN ĐƠN HÀNG THÀNH CÔNG!*\n\n"
            f"• *Mã vận đơn:* `{tracking_number}`\n"
            f"• *Mã đơn hàng:* `{order_code or '-'}`\n"
            f"• *Khách hàng:* *{full_name}*\n"
            f"• *Khối lượng dự kiến:* `{expected_weight}g`\n"
            f"• *Trạng thái:* *ĐÃ ĐĂNG KÝ (Chờ Shipper giao)*\n\n"
            f"👉 Khi Shipper giao hàng đến tủ thông minh, hệ thống sẽ tự động xác thực và gửi mã OTP lấy hàng ngay tại đây!"
        )

    @staticmethod
    def order_updated_success(
        tracking_number: str,
        order_code: Optional[str],
        full_name: str,
        expected_weight: int,
    ) -> str:
        return (
            f"🔄 *ĐÃ CẬP NHẬT ĐƠN HÀNG THÀNH CÔNG!*\n\n"
            f"• *Mã vận đơn:* `{tracking_number}`\n"
            f"• *Mã đơn hàng:* `{order_code or '-'}`\n"
            f"• *Khách hàng:* *{full_name}*\n"
            f"• *Khối lượng dự kiến:* `{expected_weight}g`\n"
            f"• *Trạng thái:* *CHỜ SHIPPER GIAO*"
        )

    # -------------------------------------------------------------------------
    # Help & Unknown Command
    # -------------------------------------------------------------------------
    @staticmethod
    def help_message() -> str:
        return (
            "🤖 *HƯỚNG DẪN SỬ DỤNG SMART PARCEL LOCKER BOT*\n\n"
            "📸 *Gửi ảnh đơn hàng:* Bạn chỉ cần gửi ảnh chụp màn hình đơn hàng Shopee/Lazada (ảnh thường hoặc file tài liệu), Bot sẽ tự nhận diện mã vận đơn & lưu đơn!\n\n"
            "📌 *Các câu lệnh tiện ích:*\n"
            "• `/orders` hoặc `/status`: Xem tất cả đơn hàng, số ngăn tủ & mã OTP lấy hàng.\n"
            "• `/check <mã_vận_đơn>`: Tra cứu tiến độ bưu kiện cụ thể.\n"
            "• `/lockers`: Xem số lượng ngăn tủ đang trống.\n"
            "• `/profile`: Xem thông tin tài khoản của bạn.\n"
            "• `/link <user_id>`: Liên kết tài khoản do Admin cấp.\n"
            "• `/unlink`: Hủy liên kết tài khoản khỏi thiết bị.\n"
            "• `/help`: Xem lại hướng dẫn này."
        )

    @staticmethod
    def invalid_command() -> str:
        return "❓ Lệnh không hợp lệ. Gõ `/help` để xem danh sách câu lệnh hỗ trợ hoặc gửi ảnh đơn hàng để lưu đơn."

