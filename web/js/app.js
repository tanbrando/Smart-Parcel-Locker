/**
 * Smart Parcel Locker - Page-specific Business Logic & API Interactivity
 */

const ic = (name) => (typeof window.faIcon === "function" ? window.faIcon(name) : "");

function escapeAttr(value) {
  return String(value ?? "").replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}

function weightCheck(o) {
  if (o.actual_weight === null || o.actual_weight === undefined) return null;
  const dev = Math.abs(o.expected_weight - o.actual_weight);
  return { dev, ok: dev <= 150 };
}

let globalLockers = [];
let globalOrders = [];
let globalUsers = [];
let globalLogs = [];

function ensureAdminSession() {
  try {
    const raw = localStorage.getItem("smartlocker_session");
    if (!raw) {
      window.location.href = "/login";
      return false;
    }
    const parsed = JSON.parse(raw);
    if (!parsed || !parsed.user) {
      window.location.href = "/login";
      return false;
    }
    if ((parsed.user.role || "USER").toUpperCase() !== "ADMIN") {
      window.location.href = "/portal";
      return false;
    }
    return true;
  } catch (_) {
    window.location.href = "/login";
    return false;
  }
}

// Fetch all common data
async function fetchAllData() {
  try {
    const [lockersRes, ordersRes, usersRes, logsRes] = await Promise.all([
      fetch(`${API_BASE}/lockers`),
      fetch(`${API_BASE}/orders`),
      fetch(`${API_BASE}/orders/users`),
      fetch(`${API_BASE}/lockers/logs`),
    ]);

    if (lockersRes.ok) globalLockers = await lockersRes.json();
    if (ordersRes.ok) globalOrders = await ordersRes.json();
    if (usersRes.ok) globalUsers = await usersRes.json();
    if (logsRes.ok) globalLogs = await logsRes.json();

    updateSidebarBadges();
  } catch (err) {
    console.error("Failed to fetch initial data:", err);
  }
}

function updateSidebarBadges() {
  const oBadge = document.getElementById("sideBadgeOrders");
  const uBadge = document.getElementById("sideBadgeUsers");
  if (oBadge) oBadge.textContent = `${globalOrders.length}`;
  if (uBadge) uBadge.textContent = `${globalUsers.length}`;
}

// -----------------------------------------------------------------------------
// 1. Dashboard Overview Page (index.html)
// -----------------------------------------------------------------------------
async function initDashboardPage() {
  if (!ensureAdminSession()) return;
  renderSharedSidebar("dashboard");
  checkGlobalHealth();
  await fetchAllData();

  renderDashboardMetrics();
  renderDashboardFunnel();
  renderDashboardLockers();
  renderDashboardRecentOrders();
  renderDashboardRecentLogs();
}

function renderDashboardMetrics() {
  const totalLockers = globalLockers.length;
  const occupiedLockers = globalLockers.filter(l => l.status === "OCCUPIED").length;
  const emptyLockers = globalLockers.filter(l => l.status === "EMPTY").length;
  const occupancyRate = totalLockers > 0 ? Math.round((occupiedLockers / totalLockers) * 100) : 0;

  const storedOrders = globalOrders.filter(o => o.status === "STORED").length;
  const pendingOrders = globalOrders.filter(o => o.status === "REGISTERED").length;
  const collectedOrders = globalOrders.filter(o => o.status === "COLLECTED").length;

  document.getElementById("kpiTotalOrders").textContent = globalOrders.length;
  document.getElementById("kpiStoredOrders").textContent = storedOrders;
  document.getElementById("kpiPendingOrders").textContent = pendingOrders;
  document.getElementById("kpiCollectedOrders").textContent = collectedOrders;
  document.getElementById("kpiOccupancyRate").textContent = `${occupancyRate}%`;
  document.getElementById("kpiEmptyCount").textContent = `${emptyLockers}/${totalLockers} trống`;
}

function renderDashboardFunnel() {
  const regCount = globalOrders.filter(o => o.status === "REGISTERED").length;
  const storedCount = globalOrders.filter(o => o.status === "STORED").length;
  const collectedCount = globalOrders.filter(o => o.status === "COLLECTED").length;
  const total = globalOrders.length || 1;

  document.getElementById("funnelRegisteredCount").textContent = `${regCount}`;
  document.getElementById("funnelStoredCount").textContent = `${storedCount}`;
  document.getElementById("funnelCollectedCount").textContent = `${collectedCount}`;

  document.getElementById("funnelRegisteredFill").style.width = `${Math.min(100, Math.round((regCount / total) * 100))}%`;
  document.getElementById("funnelStoredFill").style.width = `${Math.min(100, Math.round((storedCount / total) * 100))}%`;
  document.getElementById("funnelCollectedFill").style.width = `${Math.min(100, Math.round((collectedCount / total) * 100))}%`;
}

function renderDashboardLockers() {
  const container = document.getElementById("dashLockersList");
  if (!container) return;

  container.innerHTML = globalLockers.map(l => {
    const pct = l.max_weight > 0 ? Math.min(100, Math.round((l.current_weight / l.max_weight) * 100)) : 0;
    return `
      <div class="bento-list-item">
        <div class="item-left">
          <div class="item-avatar">#${l.locker_number}</div>
          <div class="item-text">
            <b>Ngăn ${l.locker_number}</b>
            <span>${l.current_weight}g / ${l.max_weight}g (${pct}%)</span>
          </div>
        </div>
        <span class="pill-badge ${l.status}">${l.status}</span>
      </div>
    `;
  }).join("");
}

function renderDashboardRecentOrders() {
  const container = document.getElementById("dashRecentOrdersList");
  if (!container) return;

  if (globalOrders.length === 0) {
    container.innerHTML = `<div class="text-muted" style="font-size:0.85rem; padding:10px;">Chưa có bưu kiện</div>`;
    return;
  }

  container.innerHTML = globalOrders.slice(0, 4).map(o => {
    const chk = weightCheck(o);
    const name = o.recipient_name || (o.user ? o.user.full_name : "Khách");
    return `
      <div class="bento-list-item">
        <div class="item-left">
          <div class="item-avatar">${ic("box-open")}</div>
          <div class="item-text">
            <b title="${escapeAttr(o.tracking_number)}">${o.tracking_number}</b>
            <span>${name}${chk ? ` • <span class="${chk.ok ? "text-ok" : "text-bad"}" style="display:inline;">±${chk.dev}g</span>` : ""}</span>
          </div>
        </div>
        <span class="pill-badge ${o.status}">${o.status}</span>
      </div>
    `;
  }).join("");
}

function renderDashboardRecentLogs() {
  const container = document.getElementById("dashRecentLogsList");
  if (!container) return;

  if (globalLogs.length === 0) {
    container.innerHTML = `<div class="text-muted" style="font-size:0.85rem; padding:10px;">Chưa có nhật ký</div>`;
    return;
  }

  container.innerHTML = globalLogs.slice(0, 4).map(l => {
    const time = l.created_at ? new Date(l.created_at).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" }) : "-";
    return `
      <div class="bento-list-item">
        <div class="item-left">
          <div class="item-avatar">${ic("clipboard-list")}</div>
          <div class="item-text">
            <b>${l.action}</b>
            <span title="${escapeAttr(l.details)}">${l.details || "-"}</span>
          </div>
        </div>
        <span class="text-muted" style="font-size:0.75rem; font-weight:600;">${time}</span>
      </div>
    `;
  }).join("");
}

// -----------------------------------------------------------------------------
// 2. Lockers Page (lockers.html)
// -----------------------------------------------------------------------------
async function initLockersPage() {
  if (!ensureAdminSession()) return;
  renderSharedSidebar("lockers");
  checkGlobalHealth();
  await fetchAllData();
  renderLockersGridFull();
}

function renderLockersGridFull() {
  const container = document.getElementById("lockersFullGrid");
  if (!container) return;

  container.innerHTML = globalLockers.map(l => {
    const pct = l.max_weight > 0 ? Math.min(100, Math.round((l.current_weight / l.max_weight) * 100)) : 0;
    const isMaint = l.status === "MAINTENANCE";
    const updated = l.updated_at ? new Date(l.updated_at).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" }) : "-";

    return `
      <div class="bento-card" style="display:flex; flex-direction:column; gap:14px;">
        <div class="bento-header" style="margin-bottom:0;">
          <div class="bento-title">${ic("vault")} Ngăn #${l.locker_number}</div>
          <span class="pill-badge ${l.status}">${l.status}</span>
        </div>

        <div>
          <div style="display:flex; justify-content:space-between; font-size:0.85rem; font-weight:600; margin-bottom:6px;">
            <span title="Tải trọng">${ic("weight-hanging")} ${l.current_weight}g / ${l.max_weight}g</span>
            <span>${pct}%</span>
          </div>
          <div class="stage-track" style="height:10px; margin-bottom:0;">
            <div class="stage-fill" style="width:${pct}%;"></div>
          </div>
        </div>

        <div style="display:flex; justify-content:space-between; align-items:center; gap:8px;">
          <span class="text-muted" style="font-size:0.82rem;" title="Cập nhật lần cuối">${ic("clock")} ${updated}</span>
          <button onclick="toggleLockerMaintenance(${l.id})" class="action-pill-btn secondary sm"
            title="${isMaint ? "Bật hoạt động" : "Chuyển sang bảo trì"}">
            ${ic(isMaint ? "power-off" : "wrench")} ${isMaint ? "Hoạt động" : "Bảo trì"}
          </button>
        </div>
      </div>
    `;
  }).join("");
}

async function toggleLockerMaintenance(id) {
  try {
    const res = await fetch(`${API_BASE}/lockers/${id}/maintenance`, { method: "PATCH" });
    if (res.ok) {
      await fetchAllData();
      renderLockersGridFull();
    }
  } catch (e) {
    alert("Lỗi khi chuyển trạng thái bảo trì.");
  }
}

// -----------------------------------------------------------------------------
// 3. Orders Page (orders.html)
// -----------------------------------------------------------------------------
let currentOrderFilter = "ALL";

async function initOrdersPage() {
  if (!ensureAdminSession()) return;
  renderSharedSidebar("orders");
  checkGlobalHealth();
  await fetchAllData();
  renderOrdersTable();
}

function setOrderFilter(filter) {
  currentOrderFilter = filter;
  document.querySelectorAll(".filter-pill").forEach(el => {
    el.classList.toggle("active", el.dataset.filter === filter);
  });
  renderOrdersTable();
}

function renderOrdersTable() {
  const tbody = document.querySelector("#ordersTable tbody");
  if (!tbody) return;

  const filtered = currentOrderFilter === "ALL"
    ? globalOrders
    : globalOrders.filter(o => o.status === currentOrderFilter);

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:24px; color:var(--text-muted);">Không có bưu kiện</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered.map(o => {
    const chk = weightCheck(o);
    const weight = chk
      ? `${o.expected_weight} → ${o.actual_weight}g <span class="${chk.ok ? "text-ok" : "text-bad"}" title="Lệch ${chk.dev}g">${ic(chk.ok ? "circle-check" : "triangle-exclamation")}</span>`
      : `${o.expected_weight}g`;

    return `
      <tr>
        <td>
          <code>${o.tracking_number}</code>
          <span class="cell-sub">#${o.id}${o.order_code ? ` • ${o.order_code}` : ""}</span>
        </td>
        <td><b>${o.recipient_name || (o.user ? o.user.full_name : "Khách")}</b></td>
        <td><span class="pill-badge ${o.status}">${o.status}</span></td>
        <td>${o.locker_id ? `#${o.locker_id}` : "-"}</td>
        <td style="white-space:nowrap;">${weight}</td>
        <td>${o.otp_code ? `<b><code>${o.otp_code}</code></b>` : "-"}</td>
      </tr>
    `;
  }).join("");
}

// -----------------------------------------------------------------------------
// 4. Users Page (users.html)
// -----------------------------------------------------------------------------
async function initUsersPage() {
  if (!ensureAdminSession()) return;
  renderSharedSidebar("users");
  checkGlobalHealth();
  await fetchAllData();
  renderUsersTable();

  const form = document.getElementById("createUserForm");
  if (form) {
    form.addEventListener("submit", handleCreateUser);
  }
}

function renderUsersTable() {
  const tbody = document.querySelector("#usersTable tbody");
  if (!tbody) return;

  if (globalUsers.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding:24px; color:var(--text-muted);">Chưa có tài khoản</td></tr>`;
    return;
  }

  tbody.innerHTML = globalUsers.map(u => {
    const isLinked = u.telegram_chat_id !== null && u.telegram_chat_id !== undefined;
    const tgBadge = isLinked
      ? `<span class="pill-badge REGISTERED" title="Chat ID ${u.telegram_chat_id}">Đã liên kết</span>`
      : `<span class="pill-badge" style="background:#f1f5f9; color:#64748b;" title="Kích hoạt: /start ${u.id}">Chưa</span>`;
    const faceBadge = u.face_auth_enabled
      ? `<span class="pill-badge COLLECTED">Bật ${(u.face_angles_enrolled || []).length}/5</span>`
      : u.face_registered
        ? `<span class="pill-badge OCCUPIED">Tắt</span>`
        : `<span class="pill-badge" style="background:#f1f5f9; color:#64748b;">Chưa</span>`;
    const action = isLinked
      ? `<button onclick="adminUnlinkUser(${u.id})" class="icon-btn sm danger" title="Gỡ liên kết Telegram" aria-label="Gỡ liên kết Telegram">${ic("link-slash")}</button>`
      : `<a href="/simulator" class="icon-btn sm" title="Test kích hoạt: /start ${u.id}" aria-label="Test kích hoạt Telegram">${ic("paper-plane")}</a>`;

    return `
      <tr>
        <td>
          <b>${u.full_name}</b>
          <span class="cell-sub">#${u.id}${(u.role || "USER") !== "USER" ? ` • ${u.role}` : ""}</span>
        </td>
        <td><code>${u.phone}</code></td>
        <td>${faceBadge}</td>
        <td>${tgBadge}</td>
        <td>${action}</td>
      </tr>
    `;
  }).join("");
}

async function handleCreateUser(e) {
  e.preventDefault();
  const name = document.getElementById("newFullName").value.trim();
  const phone = document.getElementById("newPhone").value.trim();
  const pwdEl = document.getElementById("newPassword");
  const password = pwdEl ? pwdEl.value.trim() || "123456" : "123456";
  const resBox = document.getElementById("createUserResult");

  try {
    const res = await fetch(`${API_BASE}/orders/users`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ full_name: name, phone: phone, password: password }),
    });

    if (res.ok) {
      const u = await res.json();
      resBox.style.display = "block";
      resBox.innerHTML = `
        <div style="background:var(--accent-yellow); color:#181816; padding:12px 16px; border-radius:14px; font-weight:600; font-size:0.88rem; margin-top:12px;">
          ${ic("circle-check")} #${u.id} ${u.full_name} • Telegram: <code>/start ${u.id}</code>
        </div>
      `;
      document.getElementById("newFullName").value = "";
      document.getElementById("newPhone").value = "";
      await fetchAllData();
      renderUsersTable();
    } else {
      const err = await res.json();
      alert("Lỗi: " + (err.detail || "Không thể tạo tài khoản"));
    }
  } catch (e) {
    alert("Lỗi kết nối.");
  }
}

async function adminUnlinkUser(userId) {
  if (confirm(`Gỡ liên kết Telegram của User #${userId}?`)) {
    await fetch(`${API_BASE}/orders/users/${userId}/unlink-telegram`, { method: "POST" });
    await fetchAllData();
    renderUsersTable();
  }
}

// -----------------------------------------------------------------------------
// 5. Logs Page (logs.html)
// -----------------------------------------------------------------------------
async function initLogsPage() {
  if (!ensureAdminSession()) return;
  renderSharedSidebar("logs");
  checkGlobalHealth();
  await fetchAllData();
  renderLogsTable();
}

function renderLogsTable() {
  const tbody = document.querySelector("#logsTable tbody");
  if (!tbody) return;

  if (globalLogs.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding:24px; color:var(--text-muted);">Chưa có nhật ký</td></tr>`;
    return;
  }

  tbody.innerHTML = globalLogs.map(l => {
    const time = l.created_at
      ? new Date(l.created_at).toLocaleString("vi-VN", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" })
      : "-";
    return `
      <tr>
        <td class="text-muted" style="font-size:0.82rem; white-space:nowrap;">${time}</td>
        <td><span class="pill-badge ${l.action}">${l.action}</span></td>
        <td>${l.locker ? `#${l.locker.locker_number}` : "-"}</td>
        <td>${l.order_id ? `#${l.order_id}` : "-"}</td>
        <td class="cell-truncate" title="${escapeAttr(l.details)}">${l.details || "-"}</td>
      </tr>
    `;
  }).join("");
}

// -----------------------------------------------------------------------------
// 6. Simulator Page (simulator.html)
// -----------------------------------------------------------------------------
async function initSimulatorPage() {
  if (!ensureAdminSession()) return;
  renderSharedSidebar("simulator");
  checkGlobalHealth();
  await fetchAllData();
}

async function sendTgSimText() {
  const chatId = parseInt(document.getElementById("simTgChatId").value, 10);
  const text = document.getElementById("simTgText").value.trim();
  const consoleBox = document.getElementById("simTgConsole");
  if (!text) return;

  consoleBox.style.display = "block";
  consoleBox.textContent += `\n> [Khách hàng ${chatId}]: ${text}\n`;

  try {
    const res = await fetch(`${API_BASE}/telegram/simulate-command`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: chatId, text: text }),
    });
    const data = await res.json();
    consoleBox.textContent += `< [SmartLocker Bot]:\n${data.response}\n`;
    consoleBox.scrollTop = consoleBox.scrollHeight;
    document.getElementById("simTgText").value = "";
    await fetchAllData();
  } catch (e) {
    consoleBox.textContent += `< [Lỗi kết nối Bot API]\n`;
  }
}

function setTgCmd(cmd) {
  document.getElementById("simTgText").value = cmd;
  sendTgSimText();
}

async function sendTgSimPhoto() {
  const chatId = parseInt(document.getElementById("simTgChatId").value, 10);
  const fileInput = document.getElementById("simTgFile");
  const consoleBox = document.getElementById("simTgConsole");

  if (!fileInput.files || fileInput.files.length === 0) {
    alert("Vui lòng chọn 1 file ảnh.");
    return;
  }

  const file = fileInput.files[0];
  const reader = new FileReader();
  reader.onload = async function(e) {
    const base64Data = e.target.result.split(",")[1];
    consoleBox.style.display = "block";
    consoleBox.textContent += `\n> [Khách ${chatId}]: [Gửi ảnh: ${file.name}]\n`;

    try {
      const res = await fetch(`${API_BASE}/telegram/simulate-command`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_id: chatId, photo_base64: base64Data, filename: file.name }),
      });
      const data = await res.json();
      consoleBox.textContent += `< [SmartLocker Bot]:\n${data.response}\n`;
      consoleBox.scrollTop = consoleBox.scrollHeight;
      fileInput.value = "";
      await fetchAllData();
    } catch (err) {
      consoleBox.textContent += `< [Lỗi bóc tách OCR ảnh]\n`;
    }
  };
  reader.readAsDataURL(file);
}

// Edge Simulator
async function simEdgeVerify() {
  const tracking = document.getElementById("simTracking").value.trim();
  const ocrWeight = parseInt(document.getElementById("simOcrWeight").value, 10) || 520;
  const box = document.getElementById("simEdgeConsole");

  box.style.display = "block";
  box.textContent += `\n> [Pi Camera] POST /pi/verify-package { tracking: "${tracking}", ocr_weight: ${ocrWeight} }\n`;

  try {
    const res = await fetch(`${API_BASE}/pi/verify-package`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tracking_number: tracking, ocr_weight: ocrWeight, recipient_phone_last4: "3456" }),
    });
    const data = await res.json();
    box.textContent += `< Status ${res.status}: ${JSON.stringify(data, null, 2)}\n`;

    if (res.ok && data.action === "UNLOCK_DOOR") {
      document.getElementById("simLockerNum").value = data.locker_number;
    }
    await fetchAllData();
  } catch (e) {
    box.textContent += `< Lỗi kết nối!\n`;
  }
}

async function simEdgeDeposit() {
  const orderId = parseInt(document.getElementById("simOrderId").value, 10);
  const lockerNum = parseInt(document.getElementById("simLockerNum").value, 10);
  const deltaWeight = parseInt(document.getElementById("simDeltaWeight").value, 10);
  const box = document.getElementById("simEdgeConsole");

  box.style.display = "block";
  box.textContent += `\n> [HX711 LoadCell] POST /pi/confirm-deposit { order: ${orderId}, locker: ${lockerNum}, weight: ${deltaWeight}g }\n`;

  try {
    const res = await fetch(`${API_BASE}/pi/confirm-deposit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ order_id: orderId, locker_number: lockerNum, delta_weight: deltaWeight }),
    });
    const data = await res.json();
    box.textContent += `< Status ${res.status}: ${JSON.stringify(data, null, 2)}\n`;

    if (res.ok && data.otp_generated) {
      document.getElementById("simOtpCode").value = data.otp_generated;
    }
    await fetchAllData();
  } catch (e) {
    box.textContent += `< Lỗi kết nối!\n`;
  }
}

async function simEdgeOtp() {
  const otp = document.getElementById("simOtpCode").value.trim();
  const box = document.getElementById("simEdgeConsole");

  box.style.display = "block";
  box.textContent += `\n> [Keypad] POST /pi/verify-otp { otp_code: "${otp}" }\n`;

  try {
    const res = await fetch(`${API_BASE}/pi/verify-otp`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ otp_code: otp }),
    });
    const data = await res.json();
    box.textContent += `< Status ${res.status}: ${JSON.stringify(data, null, 2)}\n`;
    await fetchAllData();
  } catch (e) {
    box.textContent += `< Lỗi kết nối!\n`;
  }
}
