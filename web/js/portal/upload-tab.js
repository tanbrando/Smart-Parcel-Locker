/**
 * User Portal - Upload Order Screenshot Tab Module
 * Lets users upload/capture e-commerce order screenshots for OCR registration.
 */
window.PortalUploadTab = (() => {
  let selectedFile = null;
  const icon = (name) => (typeof window.faIcon === "function" ? window.faIcon(name) : "");

  function init(user, onOrderRegistered) {
    const dropzone = document.getElementById("orderUploadDropzone");
    const fileInput = document.getElementById("orderImageInput");
    const previewImg = document.getElementById("orderPreviewImg");
    const fileNameEl = document.getElementById("orderSelectedFileName");
    const weightInput = document.getElementById("orderExpectedWeight");
    const submitBtn = document.getElementById("orderUploadSubmitBtn");
    const resultBox = document.getElementById("orderUploadResult");

    if (!dropzone || !fileInput || !submitBtn) return;

    dropzone.addEventListener("click", () => fileInput.click());

    fileInput.addEventListener("change", () => {
      if (!fileInput.files || fileInput.files.length === 0) return;
      selectedFile = fileInput.files[0];
      if (fileNameEl) {
        fileNameEl.textContent = `Đã chọn: ${selectedFile.name}`;
      }
      const reader = new FileReader();
      reader.onload = (e) => {
        if (previewImg) {
          previewImg.src = e.target.result;
          previewImg.style.display = "inline-block";
        }
      };
      reader.readAsDataURL(selectedFile);
      if (resultBox) resultBox.style.display = "none";
    });

    submitBtn.addEventListener("click", async () => {
      if (!selectedFile) {
        window.SmartAuth.showToast("Vui lòng chọn hoặc chụp ảnh đơn hàng trước.", "error");
        return;
      }

      const formData = new FormData();
      formData.append("image", selectedFile);
      formData.append("user_id", String(user.id));
      if (weightInput && weightInput.value.trim()) {
        formData.append("expected_weight", weightInput.value.trim());
      }

      submitBtn.disabled = true;
      submitBtn.innerHTML = `${icon("rotate-right")} Đang tải lên & nhận diện OCR...`;

      try {
        const res = await window.SmartApi.post("/orders/register-screenshot", formData);
        const info = res.data || {};
        if (resultBox) {
          resultBox.style.display = "block";
          resultBox.innerHTML = `
            <div style="background:var(--success-bg); color:var(--success); padding:16px; border-radius:14px; font-size:0.95rem; line-height:1.6;">
              <b>${icon("circle-check")} Đăng ký đơn hàng thành công!</b><br>
              • Mã vận đơn: <code>${info.tracking_number || "-"}</code><br>
              • Người nhận: <b>${info.detected_recipient || user.full_name}</b><br>
              • Trạng thái: <b>${info.status || "REGISTERED"}</b><br>
              ${info.message || ""}
            </div>
          `;
        }
        window.SmartAuth.showToast("Đã gửi ảnh đơn hàng thành công!");
        selectedFile = null;
        fileInput.value = "";
        if (previewImg) previewImg.style.display = "none";
        if (fileNameEl) fileNameEl.textContent = "Chạm để chọn ảnh hoặc chụp ảnh đơn hàng";
        if (typeof onOrderRegistered === "function") {
          onOrderRegistered();
        }
      } catch (err) {
        window.SmartAuth.showToast(err.message || "Không thể gửi ảnh đơn hàng.", "error");
      } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = `${icon("cloud-arrow-up")} Gửi Ảnh Đăng Ký Đơn Hàng`;
      }
    });
  }

  return { init };
})();
