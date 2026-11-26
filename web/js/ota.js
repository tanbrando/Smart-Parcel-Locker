/**
 * Smart Parcel Locker - Admin OTA Software Update Controller
 */

let _otaPollTimer = null;

function _getAuthHeaders() {
  try {
    const raw = localStorage.getItem("smartlocker_session");
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && parsed.token) {
        return { Authorization: `Bearer ${parsed.token}` };
      }
    }
  } catch (_) {}
  return {};
}

async function _otaFetch(path, options = {}) {
  const headers = Object.assign({}, _getAuthHeaders(), options.headers || {});
  const resp = await fetch(`${API_BASE}${path}`, Object.assign({}, options, { headers }));
  if (resp.status === 401 || resp.status === 403) {
    const err = await resp.json().catch(() => ({}));
    alert(err.detail || "Vui lòng đăng nhập bằng tài khoản Quản trị viên (Admin).");
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }
  return resp;
}

function _formatBytes(bytes) {
  if (!bytes) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function _formatTime(iso) {
  if (!iso) return "-";
  try {
    return new Date(iso).toLocaleString("vi-VN");
  } catch (_) {
    return iso;
  }
}

function _escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function _renderActiveJob(statusData) {
  const verEl = document.getElementById("otaCurrentVersion");
  const totalEl = document.getElementById("otaTotalReleases");
  const titleEl = document.getElementById("otaJobTitle");
  const badgeEl = document.getElementById("otaJobBadge");
  const msgEl = document.getElementById("otaJobMessage");
  const barEl = document.getElementById("otaProgressBar");

  verEl.textContent = `v${statusData.current_version || "1.0.0"}`;
  totalEl.textContent = statusData.total_releases ?? 0;

  const job = statusData.active_job || statusData.latest_job;
  if (!job) {
    titleEl.textContent = "Hệ thống đang ổn định";
    badgeEl.textContent = "IDLE";
    badgeEl.className = "ota-status-badge ota-status-SUCCESS";
    msgEl.textContent = "Chưa có tiến trình cập nhật nào.";
    barEl.style.width = "0%";
    return false;
  }

  titleEl.textContent = `Job #${job.id}: ${job.action} → v${job.target_version}`;
  badgeEl.textContent = job.status;
  badgeEl.className = `ota-status-badge ota-status-${job.status}`;
  msgEl.textContent = job.message || "";
  barEl.style.width = `${Math.max(0, Math.min(100, job.progress || 0))}%`;

  return Boolean(statusData.active_job);
}

function _renderReleases(releases, currentVersion) {
  const tbody = document.querySelector("#otaReleasesTable tbody");
  if (!releases || releases.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:20px; color:var(--text-muted);">Chưa có gói phát hành nào. Hãy tải lên file .zip ở trên.</td></tr>`;
    return;
  }

  tbody.innerHTML = releases
    .map((r) => {
      const isCurrent = r.version === currentVersion;
      return `
        <tr>
          <td><b>v${_escapeHtml(r.version)}</b> ${isCurrent ? '<span class="ota-status-badge ota-status-SUCCESS">Đang chạy</span>' : ""}</td>
          <td>${_formatBytes(r.file_size)}</td>
          <td><code title="${_escapeHtml(r.sha256)}">${_escapeHtml((r.sha256 || "").slice(0, 14))}...</code></td>
          <td>${_escapeHtml(r.changelog || "-")}</td>
          <td>${_formatTime(r.created_at)}</td>
          <td style="display:flex; gap:6px; flex-wrap:wrap;">
            <button class="ota-btn ota-btn-primary" onclick="triggerUpdate(${r.id}, '${_escapeHtml(r.version)}')">Update</button>
            <button class="ota-btn ota-btn-warning" onclick="triggerRollback('${_escapeHtml(r.version)}')">Rollback</button>
            <button class="ota-btn ota-btn-danger" onclick="deleteRelease(${r.id}, '${_escapeHtml(r.version)}')">Xóa</button>
          </td>
        </tr>`;
    })
    .join("");
}

function _renderJobs(jobs) {
  const tbody = document.querySelector("#otaJobsTable tbody");
  if (!jobs || jobs.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:20px; color:var(--text-muted);">Chưa có lịch sử cập nhật.</td></tr>`;
    return;
  }

  tbody.innerHTML = jobs
    .map(
      (j) => `
      <tr>
        <td>#${j.id}</td>
        <td><b>${_escapeHtml(j.action)}</b></td>
        <td>v${_escapeHtml(j.previous_version || "?")} → <b>v${_escapeHtml(j.target_version)}</b></td>
        <td><span class="ota-status-badge ota-status-${_escapeHtml(j.status)}">${_escapeHtml(j.status)}</span></td>
        <td>${j.progress || 0}%</td>
        <td>${_escapeHtml(j.message || "-")}</td>
      </tr>`
    )
    .join("");
}

async function refreshOtaPage() {
  try {
    const [statusResp, relResp, jobsResp] = await Promise.all([
      _otaFetch("/ota/status"),
      _otaFetch("/ota/releases"),
      _otaFetch("/ota/jobs?limit=20"),
    ]);

    const statusData = await statusResp.json();
    const releases = await relResp.json();
    const jobs = await jobsResp.json();

    const isActive = _renderActiveJob(statusData);
    _renderReleases(releases, statusData.current_version);
    _renderJobs(jobs);

    if (isActive && !_otaPollTimer) {
      _otaPollTimer = setInterval(refreshOtaPage, 2500);
    } else if (!isActive && _otaPollTimer) {
      clearInterval(_otaPollTimer);
      _otaPollTimer = null;
    }
  } catch (err) {
    console.warn("OTA refresh transient error (server may be restarting):", err);
  }
}

async function triggerUpdate(releaseId, version) {
  if (!confirm(`Xác nhận cập nhật Raspberry Pi lên phiên bản v${version}?`)) return;
  try {
    const resp = await _otaFetch("/ota/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ release_id: releaseId }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      alert(data.detail || "Không thể tạo lệnh cập nhật.");
      return;
    }
    if (!_otaPollTimer) {
      _otaPollTimer = setInterval(refreshOtaPage, 2500);
    }
    await refreshOtaPage();
  } catch (err) {
    alert("Lỗi kết nối khi gửi lệnh Update.");
  }
}

async function triggerRollback(targetVersion = null) {
  const label = targetVersion ? `v${targetVersion}` : "phiên bản trước đó";
  if (!confirm(`Xác nhận Rollback Raspberry Pi về ${label}?`)) return;
  try {
    const resp = await _otaFetch("/ota/rollback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target_version: targetVersion }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      alert(data.detail || "Không thể tạo lệnh Rollback.");
      return;
    }
    if (!_otaPollTimer) {
      _otaPollTimer = setInterval(refreshOtaPage, 2500);
    }
    await refreshOtaPage();
  } catch (err) {
    alert("Lỗi kết nối khi gửi lệnh Rollback.");
  }
}

async function deleteRelease(releaseId, version) {
  if (!confirm(`Xóa gói release v${version}?`)) return;
  const resp = await _otaFetch(`/ota/releases/${releaseId}`, { method: "DELETE" });
  const data = await resp.json();
  if (!resp.ok) {
    alert(data.detail || "Không thể xóa release.");
    return;
  }
  await refreshOtaPage();
}

document.addEventListener("DOMContentLoaded", () => {
  renderSharedSidebar("ota");

  const form = document.getElementById("otaUploadForm");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const msgEl = document.getElementById("otaUploadMsg");
    const btn = document.getElementById("otaUploadBtn");
    const version = document.getElementById("otaVersionInput").value.trim();
    const changelog = document.getElementById("otaChangelogInput").value.trim();
    const fileInput = document.getElementById("otaFileInput");

    if (!fileInput.files || !fileInput.files[0]) {
      msgEl.style.color = "#dc2626";
      msgEl.textContent = "Vui lòng chọn file .zip.";
      return;
    }

    const fd = new FormData();
    fd.append("version", version);
    fd.append("changelog", changelog);
    fd.append("file", fileInput.files[0]);

    btn.disabled = true;
    msgEl.style.color = "#2563eb";
    msgEl.textContent = "Đang tải lên, kiểm tra ZIP và ký số...";

    try {
      const resp = await _otaFetch("/ota/releases", { method: "POST", body: fd });
      const data = await resp.json();
      if (!resp.ok) {
        msgEl.style.color = "#dc2626";
        msgEl.textContent = `❌ ${data.detail || "Upload thất bại."}`;
      } else {
        msgEl.style.color = "#059669";
        msgEl.textContent = `✅ Đã tải lên thành công v${data.version} (SHA-256: ${data.sha256.slice(0, 12)}...)`;
        form.reset();
        await refreshOtaPage();
      }
    } catch (err) {
      msgEl.style.color = "#dc2626";
      msgEl.textContent = "❌ Lỗi kết nối khi tải lên.";
    } finally {
      btn.disabled = false;
    }
  });

  refreshOtaPage();
});
