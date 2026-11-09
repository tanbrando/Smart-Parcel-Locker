/**
 * Smart Parcel Locker - Shared UI Components & Sidebar Controller
 */

const API_BASE = "/api/v1";

// 1. Render Sidebar automatically on all pages
function renderSharedSidebar(activePage = "dashboard") {
  const sidebarContainer = document.getElementById("sidebarContainer");
  if (!sidebarContainer) return;

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
        <span style="font-size:0.75rem; color:var(--text-muted);">▾</span>
      </div>

      <!-- Main Navigation Links -->
      <div class="nav-section-title">Hệ Thống Quản Lý</div>
      <nav class="sidebar-nav">
        <a href="/" class="nav-link ${activePage === 'dashboard' ? 'active' : ''}">
          <span>Tổng Quan</span>
          <span class="nav-badge" id="sideBadgeLockers">3</span>
        </a>
        <a href="/orders" class="nav-link ${activePage === 'orders' ? 'active' : ''}">
          <span>Đơn Hàng & Bưu Kiện</span>
          <span class="nav-badge" id="sideBadgeOrders">-</span>
        </a>
        <a href="/lockers" class="nav-link ${activePage === 'lockers' ? 'active' : ''}">
          <span>Ngăn Tủ Vật Lý</span>
          <span class="nav-badge">3 Tủ</span>
        </a>
        <a href="/users" class="nav-link ${activePage === 'users' ? 'active' : ''}">
          <span>Khách Hàng & Telegram</span>
          <span class="nav-badge" id="sideBadgeUsers">-</span>
        </a>
        <a href="/logs" class="nav-link ${activePage === 'logs' ? 'active' : ''}">
          <span>Nhật Ký Kiểm Toán</span>
        </a>

        <div class="nav-section-title" style="margin-top:14px;">Công Cụ Kỹ Thuật</div>
        <a href="/simulator" class="nav-link ${activePage === 'simulator' ? 'active' : ''}">
          <span>Bàn Giả Lập & Test</span>
          <span class="nav-badge" style="color:var(--accent-yellow);">Console</span>
        </a>
        <a href="/docs" target="_blank" class="nav-link">
          <span>Swagger API Docs</span>
          <span class="nav-badge">↗</span>
        </a>
      </nav>

      <!-- Sidebar Footer -->
      <div class="sidebar-footer">
        <!-- AI/Bot Status Pill -->
        <div class="bot-status-card">
          <div class="bot-status-header">
            <span>Telegram Bot</span>
            <span style="font-size:0.75rem; background:#181816; color:#fff; padding:2px 7px; border-radius:9999px;">Sẵn Sàng</span>
          </div>
          <div class="bot-status-sub" id="botStatusSub">@SmartParcelLockerBot</div>
        </div>

        <!-- Admin Profile -->
        <div class="admin-profile-pill">
          <div class="admin-avatar">AD</div>
          <div class="admin-info">
            <b>Nguyễn Minh Tấn</b>
            <span>Quản trị viên trạm</span>
          </div>
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

