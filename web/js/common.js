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
          <div style="font-weight:800; font-size:1.02rem;">SmartLocker Admin</div>
          <div style="font-size:0.82rem; color:var(--text-muted);">${user.full_name}</div>
        </div>
      </div>
      <div style="display:flex; gap:6px;">
        <a href="/portal" class="mobile-logout-btn" style="text-decoration:none;">${_icon("mobile-screen")} User</a>
        <button onclick="handleSharedLogout()" class="mobile-logout-btn">${_icon("right-from-bracket")} Thoát</button>
      </div>
    `;
    mainContent.insertBefore(mobileHeader, mainContent.firstChild);
  }

  sidebarContainer.innerHTML = `
    <aside class="sidebar">
      <!-- Brand Logo -->
      <div class="sidebar-brand">
        <div class="brand-badge">PL</div>
        <div class="brand-name">SmartLocker</div>
      </div>

      <!-- Station Pill -->
      <div class="station-pill">
        <div>
          Trạm KTX Khu A
          <span>3 Ngăn Tủ Thông Minh</span>
        </div>
        <span style="font-size:0.78rem; color:var(--text-muted); font-weight:700;">ADMIN</span>
      </div>

      <!-- Main Navigation Links -->
      <div class="nav-section-title">Hệ Thống Quản Lý</div>
      <nav class="sidebar-nav">
        <a href="/" class="nav-link ${activePage === "dashboard" ? "active" : ""}">
          <span class="nav-link-content">
            <span class="nav-icon">${_icon("chart-pie")}</span>
            <span class="nav-label-full">Tổng Quan</span>
            <span class="nav-label-short">Tổng quan</span>
          </span>
          <span class="nav-badge" id="sideBadgeLockers">3</span>
        </a>
        <a href="/orders" class="nav-link ${activePage === "orders" ? "active" : ""}">
          <span class="nav-link-content">
            <span class="nav-icon">${_icon("box-open")}</span>
            <span class="nav-label-full">Đơn Hàng & Bưu Kiện</span>
            <span class="nav-label-short">Đơn hàng</span>
          </span>
          <span class="nav-badge" id="sideBadgeOrders">-</span>
        </a>
        <a href="/lockers" class="nav-link ${activePage === "lockers" ? "active" : ""}">
          <span class="nav-link-content">
            <span class="nav-icon">${_icon("vault")}</span>
            <span class="nav-label-full">Ngăn Tủ Vật Lý</span>
            <span class="nav-label-short">Ngăn tủ</span>
          </span>
          <span class="nav-badge">3 Tủ</span>
        </a>
        <a href="/users" class="nav-link ${activePage === "users" ? "active" : ""}">
          <span class="nav-link-content">
            <span class="nav-icon">${_icon("users")}</span>
            <span class="nav-label-full">Khách Hàng & Tài Khoản</span>
            <span class="nav-label-short">Khách</span>
          </span>
          <span class="nav-badge" id="sideBadgeUsers">-</span>
        </a>
        <a href="/logs" class="nav-link ${activePage === "logs" ? "active" : ""} desktop-only">
          <span class="nav-link-content">
            <span class="nav-icon">${_icon("clipboard-list")}</span>
            <span class="nav-label-full">Nhật Ký Kiểm Toán</span>
            <span class="nav-label-short">Nhật ký</span>
          </span>
        </a>

        <div class="nav-section-title" style="margin-top:14px;">Công Cụ Kỹ Thuật</div>
        <a href="/simulator" class="nav-link ${activePage === "simulator" ? "active" : ""}">
          <span class="nav-link-content">
            <span class="nav-icon">${_icon("terminal")}</span>
            <span class="nav-label-full">Bàn Giả Lập & Test</span>
            <span class="nav-label-short">Giả lập</span>
          </span>
          <span class="nav-badge" style="color:var(--accent-yellow-dark);">Console</span>
        </a>
        <a href="/portal" class="nav-link desktop-only">
          <span class="nav-link-content">
            <span class="nav-icon">${_icon("mobile-screen")}</span>
            <span class="nav-label-full">Cổng Người Dùng</span>
            <span class="nav-label-short">Portal</span>
          </span>
        </a>
        <a href="/docs" target="_blank" class="nav-link desktop-only">
          <span class="nav-link-content">
            <span class="nav-icon">${_icon("code")}</span>
            <span class="nav-label-full">Swagger API Docs</span>
          </span>
          <span class="nav-badge">↗</span>
        </a>
      </nav>

      <!-- Sidebar Footer -->
      <div class="sidebar-footer">
        <div class="bot-status-card">
          <div class="bot-status-header">
            <span>Telegram Bot</span>
            <span style="font-size:0.78rem; background:#181816; color:#fff; padding:3px 9px; border-radius:9999px;">Sẵn Sàng</span>
          </div>
          <div class="bot-status-sub" id="botStatusSub">@SmartParcelLockerBot</div>
        </div>

        <div class="admin-profile-pill" style="justify-content:space-between;">
          <div style="display:flex; align-items:center; gap:10px;">
            <div class="admin-avatar">${initials}</div>
            <div class="admin-info">
              <b>${user.full_name}</b>
              <span>Quản trị viên trạm</span>
            </div>
          </div>
          <button onclick="handleSharedLogout()" title="Đăng xuất" style="border:none; background:transparent; cursor:pointer; font-size:0.9rem; font-weight:700; color:var(--danger); display:inline-flex; align-items:center; gap:4px;">
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
