/**
 * User Portal - Orders Tracking Tab Module
 * Displays user orders with status filtering, shared-locker grouping info, and OTP copy.
 */
window.PortalOrdersTab = (() => {
  let currentFilter = "ALL";
  let cachedOrders = [];

  const icon = (name) => (typeof window.faIcon === "function" ? window.faIcon(name) : "");

  const STATUS_LABELS = {
    REGISTERED: "Chờ Shipper giao",
    STORED: "Đã giao trong tủ",
    COLLECTED: "Đã nhận hàng",
    REJECTED: "Bị từ chối",
  };

  function copyOtp(otpCode) {
    if (!otpCode) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(otpCode).then(() => {
        window.SmartAuth.showToast(`Đã sao chép mã OTP: ${otpCode}`);
      });
    } else {
      window.SmartAuth.showToast(`Mã OTP của bạn là: ${otpCode}`);
    }
  }

  function setFilter(filter) {
    currentFilter = filter;
    document.querySelectorAll("#portalOrdersFilters .filter-pill").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.filter === filter);
    });
    render(cachedOrders);
  }

  function render(ordersList) {
    cachedOrders = ordersList || [];
    const listEl = document.getElementById("portalOrdersList");
    if (!listEl) return;

    const stored = cachedOrders.filter((o) => o.status === "STORED");
    const registered = cachedOrders.filter((o) => o.status === "REGISTERED");
    const collected = cachedOrders.filter((o) => o.status === "COLLECTED");

    const elTotal = document.getElementById("userKpiTotal");
    const elStored = document.getElementById("userKpiStored");
    const elPending = document.getElementById("userKpiPending");
    const elCollected = document.getElementById("userKpiCollected");

    if (elTotal) elTotal.textContent = cachedOrders.length;
    if (elStored) elStored.textContent = stored.length;
    if (elPending) elPending.textContent = registered.length;
    if (elCollected) elCollected.textContent = collected.length;

    const storedPerLocker = {};
    stored.forEach((o) => {
      if (o.locker_id) {
        storedPerLocker[o.locker_id] = (storedPerLocker[o.locker_id] || 0) + 1;
      }
    });

    const filtered =
      currentFilter === "ALL"
        ? cachedOrders
        : cachedOrders.filter((o) => o.status === currentFilter);

    if (filtered.length === 0) {
      listEl.innerHTML = `
        <div class="empty-state-box">
          Không có đơn hàng nào trong mục này.<br>
          Hãy dùng tab <b>Gửi Ảnh Đơn</b> để đăng ký đơn hàng sắp giao!
        </div>
      `;
      return;
    }

    listEl.innerHTML = filtered
      .map((o) => {
        const isStored = o.status === "STORED";
        const sharedCount = isStored && o.locker_id ? storedPerLocker[o.locker_id] || 1 : 1;
        const createdText = o.created_at
          ? new Date(o.created_at).toLocaleString("vi-VN", {
              hour: "2-digit",
              minute: "2-digit",
              day: "2-digit",
              month: "2-digit",
            })
          : "-";

        const sharedBanner =
          isStored && sharedCount > 1
            ? `<div class="shared-locker-banner">${icon("boxes-stacked")} <span>Gộp chung ${sharedCount} đơn trong Ngăn #${o.locker_id} — Dùng chung 1 mã OTP</span></div>`
            : "";

        const otpBlock =
          isStored && o.otp_code
            ? `
              <div class="otp-highlight-box">
                <div>
                  <div style="font-size:0.78rem; opacity:0.85;">MÃ OTP MỞ NGĂN #${o.locker_id || "-"}</div>
                  <div class="otp-code-display">${o.otp_code}</div>
                </div>
                <button class="otp-copy-btn" data-copy-otp="${o.otp_code}">${icon("copy")} Sao chép</button>
              </div>
            `
            : "";

        return `
          <div class="order-card ${isStored ? "is-stored" : ""}">
            <div class="order-card-head">
              <div>
                <div class="order-tracking">${o.tracking_number || `Đơn #${o.id}`}</div>
                <div style="font-size:0.86rem; color:var(--text-muted); margin-top:2px;">
                  ${o.order_code ? `Mã đơn: ${o.order_code} • ` : ""}${createdText}
                </div>
              </div>
              <span class="pill-badge ${o.status}">${STATUS_LABELS[o.status] || o.status}</span>
            </div>

            <div class="order-meta">
              <span>${icon("vault")} Ngăn tủ: <b>${o.locker_id ? `#${o.locker_id}` : "Chưa xếp"}</b></span>
              <span>${icon("weight-hanging")} Dự kiến: <b>${o.expected_weight || 0}g</b></span>
              ${o.actual_weight !== null && o.actual_weight !== undefined ? `<span>${icon("circle-check")} Thực tế: <b>${o.actual_weight}g</b></span>` : ""}
            </div>

            ${sharedBanner}
            ${otpBlock}
          </div>
        `;
      })
      .join("");

    listEl.querySelectorAll("[data-copy-otp]").forEach((btn) => {
      btn.addEventListener("click", () => copyOtp(btn.getAttribute("data-copy-otp")));
    });
  }

  function init() {
    document.querySelectorAll("#portalOrdersFilters .filter-pill").forEach((btn) => {
      btn.addEventListener("click", () => setFilter(btn.dataset.filter));
    });
  }

  return { init, render, copyOtp };
})();
