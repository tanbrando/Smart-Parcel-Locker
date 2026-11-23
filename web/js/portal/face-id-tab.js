/**
 * User Portal - Multi-Angle Face ID Tab Module
 * 5-angle pose HUD over a live camera preview with icon-only quality telemetry
 * (light / framing / stability) and optional auto-capture.
 *
 * Live preview needs a secure context (HTTPS or localhost). When it is not
 * available (e.g. iPhone over http://<LAN-IP>), capture falls back to the
 * device's native camera via <input type="file" capture="user">.
 */
window.PortalFaceIdTab = (() => {
  const icon = (name) => (typeof window.faIcon === "function" ? window.faIcon(name) : "");
  const toast = (msg, type, ms) => window.SmartAuth.showToast(msg, type, ms);

  // Target nose coordinates are in the 400x300 HUD viewBox
  const ANGLES = [
    { key: "front", label: "Nhìn thẳng", faIcon: "face-smile", targetX: 200, targetY: 155, eyeLineY: 126, noseCurve: "M 200 62 L 200 242" },
    { key: "left", label: "Quay trái", faIcon: "arrow-left", targetX: 148, targetY: 155, eyeLineY: 126, noseCurve: "M 185 62 Q 138 152 185 242" },
    { key: "right", label: "Quay phải", faIcon: "arrow-right", targetX: 252, targetY: 155, eyeLineY: 126, noseCurve: "M 215 62 Q 262 152 215 242" },
    { key: "up", label: "Ngẩng lên", faIcon: "arrow-up", targetX: 200, targetY: 118, eyeLineY: 96, noseCurve: "M 200 58 L 200 236" },
    { key: "down", label: "Cúi xuống", faIcon: "arrow-down", targetX: 200, targetY: 190, eyeLineY: 162, noseCurve: "M 200 66 L 200 246" },
  ];

  const CAPTURE_W = 640;
  const CAPTURE_H = 480;

  let currentUser = null;
  let activeAngleIndex = 0;
  let capturedAngles = {};
  let frontNeutralPitch = null;
  let mediaStream = null;
  let analyzerTimer = null;
  let poseCheckTimer = null;
  let poseCheckInFlight = false;
  let nextAllowedCaptureAt = 0;
  let lastServerHint = "";
  let modelMissingWarned = false;
  let prevSampleData = null;
  let autoCapture = true;
  let starting = false;
  let liveFaceDot = { x: 200, y: 155, aligned: false };

  const $ = (id) => document.getElementById(id);

  // ---------------------------------------------------------------------------
  // Rendering
  // ---------------------------------------------------------------------------
  function renderHudOverlay(isAligned = false) {
    const hudEl = $("faceHudSvg");
    if (!hudEl) return;

    const angle = ANGLES[activeAngleIndex] || ANGLES[0];
    const stroke = isAligned ? "#22c55e" : "#f2ff47";
    const dash = isAligned ? "none" : "9 7";

    hudEl.innerHTML = `
      <defs>
        <mask id="faceOvalCutout">
          <rect width="400" height="300" fill="white"></rect>
          <ellipse cx="200" cy="150" rx="98" ry="118" fill="black"></ellipse>
        </mask>
      </defs>
      <rect width="400" height="300" fill="rgba(12, 12, 10, 0.48)" mask="url(#faceOvalCutout)"></rect>
      <ellipse cx="200" cy="150" rx="98" ry="118" fill="none" stroke="${stroke}" stroke-width="3.2" stroke-dasharray="${dash}"></ellipse>
      <line x1="112" y1="${angle.eyeLineY}" x2="288" y2="${angle.eyeLineY}" stroke="rgba(255,255,255,0.5)" stroke-width="1.5" stroke-dasharray="5 5"></line>
      <path d="${angle.noseCurve}" fill="none" stroke="rgba(242, 255, 71, 0.72)" stroke-width="2" stroke-dasharray="4 4"></path>
      <circle cx="${angle.targetX}" cy="${angle.targetY}" r="18" fill="rgba(242, 255, 71, 0.16)" stroke="${stroke}" stroke-width="2.5"></circle>
      <circle cx="${angle.targetX}" cy="${angle.targetY}" r="4.5" fill="${stroke}"></circle>
      ${
        mediaStream
          ? `<circle cx="${liveFaceDot.x}" cy="${liveFaceDot.y}" r="7" fill="${isAligned ? "#22c55e" : "#38bdf8"}" stroke="#ffffff" stroke-width="2"></circle>`
          : ""
      }
    `;
  }

  function isComplete() {
    return ANGLES.every((a) => capturedAngles[a.key]);
  }

  function renderAngleSteps() {
    const grid = $("faceAngleStepsGrid");
    const promptEl = $("facePromptPill");
    const saveBtn = $("faceSaveEnrollBtn");
    if (!grid) return;

    const angle = ANGLES[activeAngleIndex] || ANGLES[0];
    if (promptEl) {
      if (isComplete()) {
        promptEl.innerHTML = `${icon("circle-check")} Đủ 5 góc — Bấm Lưu`;
      } else if (lastServerHint && mediaStream) {
        promptEl.innerHTML = `${icon(angle.faIcon)} ${lastServerHint}`;
      } else {
        promptEl.innerHTML = `${icon(angle.faIcon)} ${angle.label}`;
      }
    }
    if (saveBtn) saveBtn.hidden = !isComplete();

    renderHudOverlay(liveFaceDot.aligned);

    grid.innerHTML = ANGLES.map((a, idx) => {
      const img = capturedAngles[a.key];
      const cls = `${idx === activeAngleIndex ? "current" : ""} ${img ? "captured" : ""}`;
      return `
        <button type="button" class="angle-step-card ${cls}" data-angle-idx="${idx}" title="${a.label}" aria-label="${a.label}">
          ${img ? `<img src="${img}" alt="">` : icon(a.faIcon)}
        </button>
      `;
    }).join("");

    grid.querySelectorAll("[data-angle-idx]").forEach((btn) => {
      btn.addEventListener("click", () => {
        activeAngleIndex = parseInt(btn.getAttribute("data-angle-idx"), 10);
        lastServerHint = "";
        liveFaceDot.aligned = false;
        renderAngleSteps();
      });
    });
  }

  function updateStatusUI(statusData) {
    const toggle = $("faceAuthToggleInput");
    const badge = $("faceStatusBadge");
    const enabled = Boolean(statusData.face_auth_enabled);
    const registered = Boolean(statusData.face_registered);

    if (toggle) toggle.checked = enabled;
    if (badge) {
      badge.textContent = enabled ? "Đang bật" : registered ? "Đang tắt" : "Chưa đăng ký";
      badge.className = `pill-badge ${enabled ? "COLLECTED" : registered ? "OCCUPIED" : "REGISTERED"}`;
    }
  }

  function setTelemetry(id, ok, title) {
    const el = $(id);
    if (!el) return;
    el.className = `tel-dot ${ok ? "ok" : "warn"}`;
    el.title = title;
  }

  function setLive(isLive) {
    const stage = $("faceCameraStage");
    if (stage) stage.classList.toggle("is-live", isLive);
  }

  function showCountdown(value) {
    const el = $("faceCountdownBadge");
    if (!el) return;
    el.classList.toggle("show", value !== null);
    if (value !== null) el.textContent = String(value);
  }

  // ---------------------------------------------------------------------------
  // Live frame analysis (brightness, framing, stability)
  // ---------------------------------------------------------------------------
  function analyzeVideoFrame() {
    const video = $("faceCameraVideo");
    const analysisCanvas = $("faceAnalysisCanvas");
    if (!video || !mediaStream || !analysisCanvas || video.videoWidth === 0) return;

    const w = 80;
    const h = 60;
    analysisCanvas.width = w;
    analysisCanvas.height = h;
    const ctx = analysisCanvas.getContext("2d", { willReadFrequently: true });

    // Mirror to match the preview
    ctx.save();
    ctx.scale(-1, 1);
    ctx.drawImage(video, -w, 0, w, h);
    ctx.restore();

    const frame = ctx.getImageData(0, 0, w, h).data;

    let sumLuma = 0;
    let pixels = 0;
    let weightedX = 0;
    let weightedY = 0;
    let weightTotal = 0;
    let motionDiff = 0;

    for (let y = 8; y < h - 8; y++) {
      for (let x = 16; x < w - 16; x++) {
        const idx = (y * w + x) * 4;
        const r = frame[idx];
        const g = frame[idx + 1];
        const b = frame[idx + 2];
        const luma = 0.299 * r + 0.587 * g + 0.114 * b;
        sumLuma += luma;
        pixels++;

        // Skin-tone prominence heuristic for a rough face centroid
        const isSkinLike = r > 65 && g > 40 && b > 25 && r > g && r > b && Math.abs(r - g) > 10;
        const wFactor = isSkinLike ? 3.0 : luma > 75 ? 0.6 : 0.1;
        weightedX += x * wFactor;
        weightedY += y * wFactor;
        weightTotal += wFactor;

        if (prevSampleData) motionDiff += Math.abs(luma - prevSampleData[y * w + x]);
      }
    }

    const lumaBuf = new Uint8Array(w * h);
    for (let i = 0; i < w * h; i++) {
      const p = i * 4;
      lumaBuf[i] = (0.299 * frame[p] + 0.587 * frame[p + 1] + 0.114 * frame[p + 2]) | 0;
    }
    prevSampleData = lumaBuf;

    const avgLuma = pixels > 0 ? sumLuma / pixels : 0;
    const avgMotion = pixels > 0 ? motionDiff / pixels : 99;
    const cx = weightTotal > 0 ? (weightedX / weightTotal / w) * 400 : 200;
    const cy = weightTotal > 0 ? (weightedY / weightTotal / h) * 300 : 150;

    liveFaceDot.x = Math.round(liveFaceDot.x * 0.45 + cx * 0.55);
    liveFaceDot.y = Math.round(liveFaceDot.y * 0.45 + cy * 0.55);

    const lightOk = avgLuma >= 55 && avgLuma <= 225;
    const stableOk = avgMotion < 12.5;

    setTelemetry("telLight", lightOk, avgLuma < 55 ? "Thiếu sáng" : avgLuma > 225 ? "Quá chói" : "Ánh sáng tốt");
    setTelemetry("telFrame", liveFaceDot.aligned, liveFaceDot.aligned ? "Khớp góc YuNet" : "Căn mũi vào vòng tròn");
    setTelemetry("telStable", stableOk, stableOk ? "Ổn định" : "Giữ yên đầu");

    renderHudOverlay(liveFaceDot.aligned);
  }

  function grabVideoDataUrl() {
    const video = $("faceCameraVideo");
    const canvas = $("faceCaptureCanvas");
    if (!canvas || !video || !mediaStream || video.videoWidth === 0) return null;
    canvas.width = CAPTURE_W;
    canvas.height = CAPTURE_H;
    const ctx = canvas.getContext("2d");
    drawCover(ctx, video, video.videoWidth, video.videoHeight);
    return canvas.toDataURL("image/jpeg", 0.8);
  }

  async function validateAngleWithServer(poseKey, dataUrl, isManual = false) {
    const res = await window.SmartApi.post("/auth/face/check-angle", {
      pose: poseKey,
      image: dataUrl,
      neutral_pitch: poseKey === "front" ? null : frontNeutralPitch,
    });

    if (typeof res.nose_x === "number" && typeof res.nose_y === "number") {
      liveFaceDot.x = Math.round(res.nose_x);
      liveFaceDot.y = Math.round(res.nose_y);
    }
    liveFaceDot.aligned = Boolean(res.valid);
    lastServerHint = res.message || "";

    if (res.valid) {
      if (poseKey === "front" && typeof res.neutral_pitch === "number") {
        frontNeutralPitch = res.neutral_pitch;
      }
      storeCapture(dataUrl);
      toast(res.message || `Đã chụp xong góc ${poseKey}!`, "success", 1800);
      nextAllowedCaptureAt = Date.now() + 900;
      return true;
    }

    if (isManual) {
      toast(res.message || "Tư thế chưa khớp góc yêu cầu, hãy thử lại.", "error", 3500);
    }
    renderAngleSteps();
    return false;
  }

  async function pollServerPoseCheck() {
    if (!mediaStream || poseCheckInFlight || isComplete()) return;
    if (Date.now() < nextAllowedCaptureAt) return;
    const angle = ANGLES[activeAngleIndex];
    if (!angle) return;
    // Require 'front' first so neutral_pitch is calibrated before up/down
    if (angle.key !== "front" && frontNeutralPitch === null && !capturedAngles.front) {
      activeAngleIndex = 0;
      renderAngleSteps();
      return;
    }

    const dataUrl = grabVideoDataUrl();
    if (!dataUrl) return;

    poseCheckInFlight = true;
    try {
      const res = await window.SmartApi.post("/auth/face/check-angle", {
        pose: angle.key,
        image: dataUrl,
        neutral_pitch: angle.key === "front" ? null : frontNeutralPitch,
      });

      if (typeof res.nose_x === "number" && typeof res.nose_y === "number") {
        liveFaceDot.x = Math.round(res.nose_x);
        liveFaceDot.y = Math.round(res.nose_y);
      }
      liveFaceDot.aligned = Boolean(res.valid);
      lastServerHint = res.message || "";
      setTelemetry("telFrame", liveFaceDot.aligned, res.message || "Căn mũi vào vòng tròn");

      if (res.valid && autoCapture) {
        if (angle.key === "front" && typeof res.neutral_pitch === "number") {
          frontNeutralPitch = res.neutral_pitch;
        }
        storeCapture(dataUrl);
        toast(res.message || `Đã chụp xong góc ${angle.label}!`, "success", 1800);
        nextAllowedCaptureAt = Date.now() + 1000;
      } else {
        renderAngleSteps();
      }
    } catch (err) {
      if (err && err.status === 503 && !modelMissingWarned) {
        modelMissingWarned = true;
        toast(err.message || "Chưa có model YuNet/SFace trên Server (chạy ./setup.sh).", "error", 6000);
      }
    } finally {
      poseCheckInFlight = false;
    }
  }

  // ---------------------------------------------------------------------------
  // Camera lifecycle
  // ---------------------------------------------------------------------------
  function canUseLiveCamera() {
    return Boolean(window.isSecureContext && navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
  }

  function httpsHint() {
    return `https://${location.hostname}:8443${location.pathname}`;
  }

  function describeCameraError(err) {
    switch (err && err.name) {
      case "NotAllowedError":
      case "SecurityError":
        return "Camera bị chặn. Hãy cho phép quyền camera cho trang này rồi thử lại.";
      case "NotFoundError":
      case "OverconstrainedError":
        return "Không tìm thấy camera trên thiết bị.";
      case "NotReadableError":
      case "AbortError":
        return "Camera đang được ứng dụng khác sử dụng (Zoom, Teams, Camera...). Hãy tắt ứng dụng đó rồi thử lại.";
      default:
        return "Không mở được camera.";
    }
  }

  async function requestStream() {
    const attempts = [
      { video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } }, audio: false },
      { video: { facingMode: "user" }, audio: false },
      { video: true, audio: false },
    ];
    let lastErr = null;
    for (const constraints of attempts) {
      try {
        return await navigator.mediaDevices.getUserMedia(constraints);
      } catch (err) {
        lastErr = err;
        // Permission / security errors will not be fixed by looser constraints
        if (err && (err.name === "NotAllowedError" || err.name === "SecurityError")) break;
      }
    }
    throw lastErr;
  }

  function waitForMetadata(video) {
    if (video.readyState >= 1) return Promise.resolve();
    return new Promise((resolve) => {
      const done = () => {
        video.removeEventListener("loadedmetadata", done);
        resolve();
      };
      video.addEventListener("loadedmetadata", done);
      setTimeout(done, 3000);
    });
  }

  async function startCamera() {
    if (mediaStream || starting) return;

    if (!canUseLiveCamera()) {
      // Must run synchronously inside the click so iOS allows the file picker
      openNativeCapture();
      if (!window.isSecureContext) {
        toast(`Camera trực tiếp cần HTTPS — đang dùng camera của máy. Mở ${httpsHint()} để có khung căn mặt.`, "error", 6500);
      }
      return;
    }

    const video = $("faceCameraVideo");
    if (!video) return;

    starting = true;
    try {
      const stream = await requestStream();
      mediaStream = stream;

      video.muted = true;
      video.playsInline = true;
      video.setAttribute("playsinline", "");
      video.setAttribute("muted", "");
      video.srcObject = stream;
      await waitForMetadata(video);
      await video.play().catch(() => {});

      prevSampleData = null;
      lastServerHint = "";
      nextAllowedCaptureAt = Date.now() + 600;
      setLive(true);
      if (analyzerTimer) clearInterval(analyzerTimer);
      if (poseCheckTimer) clearInterval(poseCheckTimer);
      analyzerTimer = setInterval(analyzeVideoFrame, 180);
      poseCheckTimer = setInterval(pollServerPoseCheck, 650);
      renderAngleSteps();
    } catch (err) {
      stopCamera();
      toast(`${describeCameraError(err)} Có thể bấm nút chụp để dùng camera của máy.`, "error", 6000);
    } finally {
      starting = false;
    }
  }

  function stopCamera() {
    if (analyzerTimer) {
      clearInterval(analyzerTimer);
      analyzerTimer = null;
    }
    if (poseCheckTimer) {
      clearInterval(poseCheckTimer);
      poseCheckTimer = null;
    }
    poseCheckInFlight = false;
    if (mediaStream) {
      mediaStream.getTracks().forEach((t) => t.stop());
      mediaStream = null;
    }
    const video = $("faceCameraVideo");
    if (video) video.srcObject = null;
    liveFaceDot.aligned = false;
    lastServerHint = "";
    showCountdown(null);
    setLive(false);
    renderHudOverlay(false);
  }

  // ---------------------------------------------------------------------------
  // Capture
  // ---------------------------------------------------------------------------
  function storeCapture(dataUrl) {
    const angle = ANGLES[activeAngleIndex];
    capturedAngles[angle.key] = dataUrl;

    const nextMissing = ANGLES.findIndex((a) => !capturedAngles[a.key]);
    if (nextMissing !== -1) activeAngleIndex = nextMissing;
    lastServerHint = "";
    liveFaceDot.aligned = false;
    renderAngleSteps();
  }

  async function captureFromVideo() {
    const dataUrl = grabVideoDataUrl();
    if (!dataUrl || poseCheckInFlight) return;
    const angle = ANGLES[activeAngleIndex];
    if (!angle) return;

    poseCheckInFlight = true;
    try {
      await validateAngleWithServer(angle.key, dataUrl, true);
    } catch (err) {
      toast(err.message || "Không thể kiểm tra góc khuôn mặt.", "error", 4000);
    } finally {
      poseCheckInFlight = false;
    }
  }

  // Center-crop source into the 4:3 capture canvas (like object-fit: cover)
  function drawCover(ctx, source, srcW, srcH, dx = 0, dy = 0) {
    const targetRatio = CAPTURE_W / CAPTURE_H;
    let sw = srcW;
    let sh = srcH;
    if (srcW / srcH > targetRatio) sw = srcH * targetRatio;
    else sh = srcW / targetRatio;
    const sx = (srcW - sw) / 2;
    const sy = (srcH - sh) / 2;
    ctx.drawImage(source, sx, sy, sw, sh, dx, dy, CAPTURE_W, CAPTURE_H);
  }

  function openNativeCapture() {
    const input = $("faceNativeCaptureInput");
    if (input) {
      input.value = "";
      input.click();
    }
  }

  function handleNativeFile() {
    const input = $("faceNativeCaptureInput");
    const canvas = $("faceCaptureCanvas");
    if (!input || !canvas || !input.files || input.files.length === 0) return;

    const url = URL.createObjectURL(input.files[0]);
    const img = new Image();
    img.onload = async () => {
      canvas.width = CAPTURE_W;
      canvas.height = CAPTURE_H;
      drawCover(canvas.getContext("2d"), img, img.naturalWidth, img.naturalHeight);
      URL.revokeObjectURL(url);
      const dataUrl = canvas.toDataURL("image/jpeg", 0.8);
      const angle = ANGLES[activeAngleIndex];
      try {
        await validateAngleWithServer(angle.key, dataUrl, true);
      } catch (err) {
        toast(err.message || "Không thể kiểm tra ảnh vừa chụp.", "error", 4000);
      }
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      toast("Không đọc được ảnh vừa chụp.", "error");
    };
    img.src = url;
  }

  function handleShutter() {
    if (mediaStream) captureFromVideo();
    else openNativeCapture();
  }

  function toggleAutoCapture() {
    autoCapture = !autoCapture;
    const btn = $("faceAutoCaptureBtn");
    if (btn) {
      btn.classList.toggle("is-on", autoCapture);
      btn.setAttribute("aria-pressed", String(autoCapture));
      btn.title = `Tự động chụp: ${autoCapture ? "bật" : "tắt"}`;
    }
    if (!autoCapture) {
      showCountdown(null);
    }
  }

  // ---------------------------------------------------------------------------
  // API
  // ---------------------------------------------------------------------------
  async function saveEnrollment() {
    if (!currentUser || !isComplete()) return;
    const saveBtn = $("faceSaveEnrollBtn");
    if (saveBtn) {
      saveBtn.disabled = true;
      saveBtn.innerHTML = `${icon("rotate-right")} Đang lưu...`;
    }

    try {
      const res = await window.SmartApi.post("/auth/face/enroll", {
        user_id: currentUser.id,
        angles: capturedAngles,
      });
      updateStatusUI(res);
      window.SmartAuth.updateSessionUser({
        face_auth_enabled: res.face_auth_enabled,
        face_registered: res.face_registered,
        face_angles_enrolled: res.enrolled_angles,
      });
      stopCamera();
      toast(res.message || "Đã lưu Face ID.");
    } catch (err) {
      toast(err.message || "Lỗi khi lưu dữ liệu khuôn mặt.", "error");
    } finally {
      if (saveBtn) {
        saveBtn.disabled = false;
        saveBtn.innerHTML = `${icon("circle-check")} Lưu Face ID`;
      }
    }
  }

  async function handleToggleChange(e) {
    if (!currentUser) return;
    const enabled = e.target.checked;
    try {
      const res = await window.SmartApi.post("/auth/face/toggle", { user_id: currentUser.id, enabled });
      updateStatusUI(res);
      window.SmartAuth.updateSessionUser({ face_auth_enabled: res.face_auth_enabled });
      toast(res.message);
    } catch (err) {
      e.target.checked = !enabled;
      toast(err.message || "Không thể thay đổi trạng thái Face ID.", "error");
    }
  }

  async function refreshStatus() {
    if (!currentUser) return;
    try {
      updateStatusUI(await window.SmartApi.get(`/auth/face/status/${currentUser.id}`));
    } catch (_) {}
  }

  function init(user) {
    currentUser = user;
    const accountId = $("facePickupAccountId");
    if (accountId) accountId.textContent = `Mã tài khoản tại tủ: ${user.id}`;
    renderAngleSteps();
    refreshStatus();

    const on = (id, evt, fn) => {
      const el = $(id);
      if (el) el.addEventListener(evt, fn);
    };

    on("faceAuthToggleInput", "change", handleToggleChange);
    on("faceStartCameraBtn", "click", startCamera);
    on("faceCaptureAngleBtn", "click", handleShutter);
    on("faceAutoCaptureBtn", "click", toggleAutoCapture);
    on("faceNativeCaptureInput", "change", handleNativeFile);
    on("faceSaveEnrollBtn", "click", saveEnrollment);
    on("faceResetAnglesBtn", "click", () => {
      capturedAngles = {};
      frontNeutralPitch = null;
      activeAngleIndex = 0;
      lastServerHint = "";
      liveFaceDot.aligned = false;
      renderAngleSteps();
    });

    // Release the camera when the page is hidden (tab switch, app switch on iOS)
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) stopCamera();
    });
    window.addEventListener("pagehide", stopCamera);
  }

  return { init, stopCamera, refreshStatus };
})();
