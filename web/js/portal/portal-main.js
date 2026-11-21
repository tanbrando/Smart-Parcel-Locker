/**
 * User Portal Main Coordinator
 * Handles session guard, responsive navigation (Left Sidebar on PC / Horizontal Bottom Menu on Mobile),
 * tab switching, and live notification polling using FontAwesome SVG icons.
 */
(() => {
  let activeTab = "orders";
  let currentUser = null;

  const icon = (name) => (typeof window.faIcon === "function" ? window.faIcon(name) : "");

  function renderPortalNavigation(user) {
    const container = document.getElementById("sidebarContainer");
    if (!container) return;

    const initials = (user.full_name || "US")
      .split(" ")
      .map((w) => w[0])
      .join("")
      .slice(-2)
      .toUpperCase();

    const isAdmin = (user.role || "").toUpperCase() === "ADMIN";

    container.innerHTML = `
      <aside class="sidebar">
        <div class="sidebar-brand">
          <div class="brand-badge">PL</div>
          <div class="brand-name">SmartLocker</div>
        </div>

        <nav class="sidebar-nav">
          <button type="button" class="nav-link ${activeTab === "orders" ? "active" : ""}" data-tab="orders">
            <span class="nav-link-content">
              <span class="nav-icon">${icon("box-open")}</span>
              <span class="nav-label-full">Đơn hàng</span>
              <span class="nav-label-short">Đơn hàng</span>
            </span>
          </button>

          <button type="button" class="nav-link ${activeTab === "upload" ? "active" : ""}" data-tab="upload">
            <span class="nav-link-content">
              <span class="nav-icon">${icon("camera")}</span>
              <span class="nav-label-full">Gửi ảnh</span>
              <span class="nav-label-short">Gửi ảnh</span>
            </span>
          </button>

          <button type="button" class="nav-link ${activeTab === "faceid" ? "active" : ""}" data-tab="faceid">
            <span class="nav-link-content">
              <span class="nav-icon">${icon("id-card")}</span>
              <span class="nav-label-full">Face ID</span>
              <span class="nav-label-short">Face ID</span>
            </span>
          </button>

          <button type="button" class="nav-link ${activeTab === "notifications" ? "active" : ""}" data-tab="notifications">
            <span class="nav-link-content">
              <span class="nav-icon">${icon("bell")}</span>
              <span class="nav-label-full">Thông báo</span>
              <span class="nav-label-short">Thông báo</span>
            </span>
            <span class="nav-notif-dot" id="navNotifBadge" style="display:none;">0</span>
          </button>

          ${
            isAdmin
              ? `
                <a href="/" class="nav-link desktop-only">
                  <span class="nav-link-content">
                    <span class="nav-icon">${icon("gear")}</span>
                    <span class="nav-label-full">Quản trị</span>
                  </span>
                </a>
              `
              : ""
          }
        </nav>

        <div class="sidebar-footer">
          <div class="admin-profile-pill" style="justify-content:space-between;">
            <div style="display:flex; align-items:center; gap:10px;">
              <div class="admin-avatar">${initials}</div>
              <div class="admin-info">
                <b>${user.full_name}</b>
                <span>${user.phone || `#${user.id}`}</span>
              </div>
            </div>
            <button type="button" id="desktopLogoutBtn" title="Đăng xuất" style="border:none; background:transparent; cursor:pointer; font-size:0.95rem; font-weight:700; color:var(--danger); display:inline-flex; align-items:center; gap:4px;">
              ${icon("right-from-bracket")}
            </button>
          </div>
        </div>
      </aside>
    `;

    container.querySelectorAll("[data-tab]").forEach((btn) => {
      btn.addEventListener("click", () => switchTab(btn.getAttribute("data-tab")));
    });

    const logoutBtn = document.getElementById("desktopLogoutBtn");
    if (logoutBtn) logoutBtn.addEventListener("click", () => window.SmartAuth.logout());
  }

  function switchTab(tabName) {
    activeTab = tabName;
    if (tabName !== "faceid" && window.PortalFaceIdTab) {
      window.PortalFaceIdTab.stopCamera();
    }

    document.querySelectorAll(".portal-tab-panel").forEach((panel) => {
      panel.classList.toggle("active", panel.id === `tab-${tabName}`);
    });

    document.querySelectorAll("#sidebarContainer [data-tab]").forEach((btn) => {
      const isActive = btn.getAttribute("data-tab") === tabName;
      btn.classList.toggle("active", isActive);
    });
  }

  async function refreshPortalData() {
    if (!currentUser) return;
    try {
      const [ordersData, notifData] = await Promise.all([
        window.SmartApi.get(`/orders?user_id=${currentUser.id}`),
        window.SmartApi.get(`/orders/user/${currentUser.id}/notifications`),
      ]);
      window.PortalOrdersTab.render(ordersData);
      window.PortalNotificationsTab.render(notifData);
    } catch (err) {
      console.error("Failed to refresh portal data:", err);
    }
  }

  document.addEventListener("DOMContentLoaded", async () => {
    const session = window.SmartAuth.getSession();
    if (!session || !session.user) {
      window.location.href = "/login";
      return;
    }

    currentUser = session.user;

    const greetingName = document.getElementById("portalUserName");
    const mobileUserName = document.getElementById("mobilePortalUserName");
    if (greetingName) greetingName.textContent = currentUser.full_name;
    if (mobileUserName) mobileUserName.textContent = currentUser.full_name;

    const mobileLogout = document.getElementById("mobileLogoutBtn");
    if (mobileLogout) mobileLogout.addEventListener("click", () => window.SmartAuth.logout());

    const refreshBtn = document.getElementById("portalRefreshBtn");
    if (refreshBtn) refreshBtn.addEventListener("click", refreshPortalData);

    renderPortalNavigation(currentUser);
    window.PortalOrdersTab.init();
    window.PortalUploadTab.init(currentUser, async () => {
      await refreshPortalData();
      switchTab("orders");
    });
    window.PortalFaceIdTab.init(currentUser);

    await refreshPortalData();

    setInterval(refreshPortalData, 12000);
  });
})();
