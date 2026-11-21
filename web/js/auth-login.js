/**
 * Login Page Controller (User & Admin Authentication)
 */
document.addEventListener("DOMContentLoaded", () => {
  // If already logged in, redirect to appropriate workspace
  const existing = window.SmartAuth.getSession();
  if (existing && existing.user) {
    const role = (existing.user.role || "USER").toUpperCase();
    window.location.href = role === "ADMIN" ? "/" : "/portal";
    return;
  }

  const form = document.getElementById("loginForm");
  const phoneInput = document.getElementById("loginPhone");
  const passwordInput = document.getElementById("loginPassword");
  const errorBox = document.getElementById("loginErrorBox");
  const submitBtn = document.getElementById("loginSubmitBtn");

  // Demo quick-fill buttons
  document.querySelectorAll("[data-demo-phone]").forEach((btn) => {
    btn.addEventListener("click", () => {
      phoneInput.value = btn.getAttribute("data-demo-phone") || "";
      passwordInput.value = btn.getAttribute("data-demo-pass") || "";
      errorBox.style.display = "none";
    });
  });

  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      errorBox.style.display = "none";
      const phone = phoneInput.value.trim();
      const password = passwordInput.value;

      if (!phone || !password) {
        errorBox.textContent = "Vui lòng nhập đầy đủ số điện thoại và mật khẩu.";
        errorBox.style.display = "block";
        return;
      }

      submitBtn.disabled = true;
      submitBtn.textContent = "Đang xác thực...";

      try {
        const res = await window.SmartApi.post("/auth/login", { phone, password });
        window.SmartAuth.saveSession(res);
        window.location.href = res.redirect_url || "/portal";
      } catch (err) {
        errorBox.textContent = err.message || "Đăng nhập thất bại. Vui lòng thử lại.";
        errorBox.style.display = "block";
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "Đăng Nhập";
      }
    });
  }
});
