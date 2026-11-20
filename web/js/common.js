/**
 * Smart Parcel Locker - Shared Admin Navigation Controller
 * Renders Left Sidebar on Desktop/Laptop and Fixed Horizontal Bottom Menu on Mobile.
 * Uses FontAwesome 6 Inline SVG icons.
 */

const API_BASE = "/api/v1";

function _icon(name) {
  return typeof window.faIcon === "function" ? window.faIcon(name) : "";
}

function _getCurrentAdminUser() {
  try {
    const raw = localStorage.getItem("smartlocker_session");
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && parsed.user) return parsed.user;
    }
  } catch (_) {}
  return { full_name: "Quản trị viên", role: "ADMIN" };
}

function handleSharedLogout() {
  localStorage.removeItem("smartlocker_session");
  window.location.href = "/login";
}

// 1. Render Admin Sidebar (Left on Desktop, Horizontal Bottom Menu on Mobile)
function renderSharedSidebar(activePage = "dashboard") {
  const sidebarContainer = document.getElementById("sidebarContainer");
  if (!sidebarContainer) return;

  const user = _getCurrentAdminUser();
  const initials = (user.full_name || "AD")
    .split(" ")
    .map((w) => w[0])
    .join("")
    .slice(-2)
    .toUpperCase();

  // Inject compact mobile header for admin pages if not present
  const mainContent = document.querySelector(".main-content");
  if (mainContent && !document.getElementById("adminMobileTopHeader")) {
    const mobileHeader = document.createElement("div");
    mobileHeader.id = "adminMobileTopHeader";
    mobileHeader.className = "mobile-top-header";
    mobileHeader.innerHTML = `
      <div class="mobile-top-user">
        <div class="brand-badge">PL</div>
        <div>
          <div style="font-weight:800; font-size:1.02rem;">SmartLocker</div>
          <div style="font-size:0.82rem; color:var(--text-muted);">${user.full_name}</div>
        </div>
      </div>
      <div style="display:flex; gap:6px;">
        <a href="/logs" class="icon-btn" title="Nhật ký" aria-label="Nhật ký">${_icon("clipboard-list")}</a>
        <a href="/portal" class="icon-btn" title="Cổng người dùng" aria-label="Cổng người dùng">${_icon("mobile-screen")}</a>
        <button onclick="handleSharedLogout()" class="icon-btn danger" title="Đăng xuất" aria-label="Đăng xuất">${_icon("right-from-bracket")}</button>
      </div>
    `;
    mainContent.insertBefore(mobileHeader, mainContent.firstChild);
  }

  const link = (page, href, iconName, full, short, badge = "", extraClass = "") => `
    <a href="${href}" class="nav-link ${activePage === page ? "active" : ""} ${extraClass}">
      <span class="nav-link-content">
        <span class="nav-icon">${_icon(iconName)}</span>
        <span class="nav-label-full">${full}</span>
        ${short ? `<span class="nav-label-short">${short}</span>` : ""}
      </span>
      ${badge}
    </a>`;

  sidebarContainer.innerHTML = `
    <aside class="sidebar">
      <div class="sidebar-brand">
        <div class="brand-badge">PL</div>
        <div class="brand-name">SmartLocker</div>
      </div>

      <nav class="sidebar-nav">
        ${link("dashboard", "/", "chart-pie", "Tổng quan", "Tổng quan")}
        ${link("orders", "/orders", "box-open", "Đơn hàng", "Đơn hàng", `<span class="nav-badge" id="sideBadgeOrders"></span>`)}
        ${link("lockers", "/lockers", "vault", "Ngăn tủ", "Ngăn tủ")}
        ${link("users", "/users", "users", "Khách hàng", "Khách", `<span class="nav-badge" id="sideBadgeUsers"></span>`)}
        ${link("logs", "/logs", "clipboard-list", "Nhật ký", "Nhật ký", "", "desktop-only")}
        ${link("simulator", "/simulator", "terminal", "Giả lập", "Giả lập")}
        ${link("portal", "/portal", "mobile-screen", "Cổng người dùng", "", "", "desktop-only")}
        <a href="/docs" target="_blank" rel="noopener" class="nav-link desktop-only">
          <span class="nav-link-content">
            <span class="nav-icon">${_icon("code")}</span>
            <span class="nav-label-full">API Docs</span>
          </span>
          <span class="nav-badge">${_icon("arrow-up-right-from-square")}</span>
        </a>
      </nav>

      <div class="sidebar-footer">
        <div class="admin-profile-pill" style="justify-content:space-between;">
          <div style="display:flex; align-items:center; gap:10px; min-width:0;">
            <div class="admin-avatar">${initials}</div>
            <div class="admin-info">
              <b>${user.full_name}</b>
              <span>Admin</span>
            </div>
          </div>
          <button onclick="handleSharedLogout()" class="icon-btn sm danger" title="Đăng xuất" aria-label="Đăng xuất">
            ${_icon("right-from-bracket")}
          </button>
        </div>
      </div>
    </aside>
  `;
}

// 2. Global Health Check
async function checkGlobalHealth() {
  try {
    const res = await fetch("/health");
    const indicator = document.getElementById("healthStatusIndicator");
    if (indicator) {
      if (res.ok) {
        indicator.textContent = "Hệ Thống Trực Tuyến";
        indicator.style.color = "var(--success)";
      } else {
        indicator.textContent = "Máy Chủ Mất Kết Nối";
        indicator.style.color = "var(--danger)";
      }
    }
  } catch (e) {
    const indicator = document.getElementById("healthStatusIndicator");
    if (indicator) {
      indicator.textContent = "Offline";
      indicator.style.color = "var(--danger)";
    }
  }
}
