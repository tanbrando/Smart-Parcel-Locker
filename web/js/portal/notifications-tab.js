/**
 * User Portal - Notifications & OTP Alerts Tab Module
 * Polls for newly delivered orders and displays actionable OTP cards.
 */
window.PortalNotificationsTab = (() => {
  let knownStoredIds = new Set();
  let initialized = false;
  const icon = (name) => (typeof window.faIcon === "function" ? window.faIcon(name) : "");

  function render(notifications) {
    const listEl = document.getElementById("portalNotificationsList");
    const badgeEl = document.getElementById("navNotifBadge");
    if (!listEl) return;

    const storedAlerts = (notifications || []).filter((n) => n.status === "STORED");

    if (initialized) {
      storedAlerts.forEach((n) => {
        if (!knownStoredIds.has(n.order_id)) {
          window.SmartAuth.showToast(
            `Đơn ${n.tracking_number} đã giao vào Ngăn #${n.locker_number} — OTP: ${n.otp_code}`,
            "success",
            5500
          );
        }
      });
    }
    knownStoredIds = new Set(storedAlerts.map((n) => n.order_id));
    initialized = true;

    if (badgeEl) {
      if (storedAlerts.length > 0) {
        badgeEl.textContent = String(storedAlerts.length);
        badgeEl.style.display = "inline-flex";
      } else {
        badgeEl.style.display = "none";
      }
    }

    if (!notifications || notifications.length === 0) {
      listEl.innerHTML = `
        <div class="empty-state-box">${icon("bell")}Chưa có thông báo</div>
      `;
      return;
    }

    listEl.innerHTML = notifications
      .map((n) => {
        const isStored = n.status === "STORED";
        const timeStr = (n.delivered_at || n.collected_at)
          ? new Date(n.delivered_at || n.collected_at).toLocaleString("vi-VN")
          : "Vừa xong";

        return `
          <div class="notif-card ${isStored ? "unread" : ""}">
            <div style="display:flex; justify-content:space-between; align-items:center; gap:8px;">
              <span class="pill-badge ${n.status}">${isStored ? "Chờ lấy" : "Đã nhận"}</span>
              <span style="font-size:0.84rem; color:var(--text-muted);">${timeStr}</span>
            </div>
            <div style="font-size:0.98rem; font-weight:600; color:var(--text-dark); line-height:1.5;">
              ${n.message}
            </div>
            ${
              isStored && n.otp_code
                ? `
                  <div class="otp-highlight-box">
                    <div>
                      <div style="font-size:0.78rem; opacity:0.85;">${icon("vault")} Ngăn #${n.locker_number || "-"}</div>
                      <div class="otp-code-display">${n.otp_code}</div>
                    </div>
                    <button class="otp-copy-btn" data-notif-otp="${n.otp_code}" title="Sao chép" aria-label="Sao chép OTP">${icon("copy")}</button>
                  </div>
                `
                : ""
            }
          </div>
        `;
      })
      .join("");

    listEl.querySelectorAll("[data-notif-otp]").forEach((btn) => {
      btn.addEventListener("click", () => {
        window.PortalOrdersTab.copyOtp(btn.getAttribute("data-notif-otp"));
      });
    });
  }

  return { render };
})();
