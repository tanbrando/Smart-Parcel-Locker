/**
 * User Portal - Orders Tracking Tab Module
 * Displays user orders with status filtering, shared-locker grouping info, and OTP copy.
 */
window.PortalOrdersTab = (() => {
  let currentFilter = "ALL";
  let cachedOrders = [];

  const icon = (name) => (typeof window.faIcon === "function" ? window.faIcon(name) : "");

  const STATUS_LABELS = {
    REGISTERED: "Chờ giao",
    STORED: "Trong tủ",
    COLLECTED: "Đã nhận",
    REJECTED: "Từ chối",
  };

  function copyOtp(otpCode) {
    if (!otpCode) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(otpCode).then(() => {
        window.SmartAuth.showToast(`Đã sao chép OTP ${otpCode}`);
      });
    } else {
      window.SmartAuth.showToast(`OTP: ${otpCode}`);
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
        <div class="empty-state-box">${icon("box-open")}Không có đơn hàng</div>
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
            ? `<div class="shared-locker-banner" title="Các đơn trong cùng ngăn dùng chung 1 mã OTP">${icon("boxes-stacked")} <span>${sharedCount} đơn chung ngăn #${o.locker_id}</span></div>`
            : "";

        const otpBlock =
          isStored && o.otp_code
            ? `
              <div class="otp-highlight-box">
                <div>
                  <div style="font-size:0.78rem; opacity:0.85;">${icon("vault")} Ngăn #${o.locker_id || "-"}</div>
                  <div class="otp-code-display">${o.otp_code}</div>
                </div>
                <button class="otp-copy-btn" data-copy-otp="${o.otp_code}" title="Sao chép" aria-label="Sao chép OTP">${icon("copy")}</button>
              </div>
            `
            : "";

        return `
          <div class="order-card ${isStored ? "is-stored" : ""}">
            <div class="order-card-head">
              <div style="min-width:0;">
                <div class="order-tracking">${o.tracking_number || `Đơn #${o.id}`}</div>
                <div style="font-size:0.86rem; color:var(--text-muted); margin-top:2px;">
                  ${o.order_code ? `${o.order_code} • ` : ""}${createdText}
                </div>
              </div>
              <span class="pill-badge ${o.status}">${STATUS_LABELS[o.status] || o.status}</span>
            </div>

            <div class="order-meta">
              <span title="Ngăn tủ">${icon("vault")} <b>${o.locker_id ? `#${o.locker_id}` : "-"}</b></span>
              <span title="Khối lượng dự kiến → thực tế">${icon("weight-hanging")} <b>${o.expected_weight || 0}g${o.actual_weight != null ? ` → ${o.actual_weight}g` : ""}</b></span>
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
