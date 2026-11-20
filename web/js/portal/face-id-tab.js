/**
 * User Portal - Interactive Multi-Angle Face ID Tab Module
 * Provides a 5-angle 3D Pose Alignment SVG HUD, live camera quality telemetry
 * (brightness, framing, stability), and optional auto-capture countdown.
 */
window.PortalFaceIdTab = (() => {
  const icon = (name) => (typeof window.faIcon === "function" ? window.faIcon(name) : "");

  // Detailed 5-angle alignment specs with target nose coordinates (in 400x300 HUD viewBox)
  const ANGLES = [
    {
      key: "front",
      label: "Chính diện",
      faIcon: "face-smile",
      shortPrompt: "Nhìn thẳng • Đặt mũi vào tâm vòng tròn",
      detailTitle: "Góc 1/5: Chính diện (0°)",
      detailInstruction:
        "Giữ đầu thẳng, đặt 2 mắt ngang đường kẻ mắt và mũi nằm ngay vòng tròn tâm ở giữa khung.",
      targetX: 200,
      targetY: 155,
      eyeLineY: 126,
      noseCurve: "M 200 62 L 200 242",
    },
    {
      key: "left",
      label: "Quay trái",
      faIcon: "arrow-left",
      shortPrompt: "Quay mặt sang TRÁI (~30°) chạm tâm đỏ/vàng",
      detailTitle: "Góc 2/5: Quay trái (-30°)",
      detailInstruction:
        "Xoay nhẹ đầu sang trái khoảng 30° sao cho đầu mũi hướng về vòng tròn đích bên TRÁI, mắt vẫn nhìn vào khung.",
      targetX: 148,
      targetY: 155,
      eyeLineY: 126,
      noseCurve: "M 185 62 Q 138 152 185 242",
    },
    {
      key: "right",
      label: "Quay phải",
      faIcon: "arrow-right",
      shortPrompt: "Quay mặt sang PHẢI (~30°) chạm tâm đích",
      detailTitle: "Góc 3/5: Quay phải (+30°)",
      detailInstruction:
        "Xoay nhẹ đầu sang phải khoảng 30° sao cho đầu mũi hướng về vòng tròn đích bên PHẢI, giữ mặt trong khung bầu dục.",
      targetX: 252,
      targetY: 155,
      eyeLineY: 126,
      noseCurve: "M 215 62 Q 262 152 215 242",
    },
    {
      key: "up",
      label: "Ngẩng lên",
      faIcon: "arrow-up",
      shortPrompt: "Ngẩng nhẹ cằm LÊN TRÊN (~20°)",
      detailTitle: "Góc 4/5: Ngẩng lên (+20°)",
      detailInstruction:
        "Nâng nhẹ cằm lên khoảng 20° sao cho tầm mắt khớp với đường kẻ ngang phía TRÊN và mũi chạm điểm đích trên.",
      targetX: 200,
      targetY: 118,
      eyeLineY: 96,
      noseCurve: "M 200 58 L 200 236",
    },
    {
      key: "down",
      label: "Cúi xuống",
      faIcon: "arrow-down",
      shortPrompt: "Cúi nhẹ cằm XUỐNG DƯỚI (~20°)",
      detailTitle: "Góc 5/5: Cúi xuống (-20°)",
      detailInstruction:
        "Hạ nhẹ cằm xuống khoảng 20° sao cho mắt khớp đường kẻ ngang phía DƯỚI và đầu mũi chạm điểm đích dưới.",
      targetX: 200,
      targetY: 190,
      eyeLineY: 162,
      noseCurve: "M 200 66 L 200 246",
    },
  ];

  let currentUser = null;
  let activeAngleIndex = 0;
  let capturedAngles = {};
  let mediaStream = null;
  let analyzerTimer = null;
  let prevSampleData = null;
  let stableAlignedTicks = 0;
  let liveFaceDot = { x: 200, y: 155, aligned: false };

  function renderHudOverlay(isAligned = false) {
    const hudEl = document.getElementById("faceHudSvg");
    if (!hudEl) return;

    const angle = ANGLES[activeAngleIndex] || ANGLES[0];
    const ovalStroke = isAligned ? "#22c55e" : "#f2ff47";
    const ovalDash = isAligned ? "none" : "9 7";

    hudEl.innerHTML = `
      <defs>
        <mask id="faceOvalCutout">
          <rect width="400" height="300" fill="white"></rect>
          <ellipse cx="200" cy="150" rx="98" ry="118" fill="black"></ellipse>
        </mask>
      </defs>
      <!-- Dimmed outside mask -->
      <rect width="400" height="300" fill="rgba(12, 12, 10, 0.48)" mask="url(#faceOvalCutout)"></rect>

      <!-- Main Face Oval Guide -->
      <ellipse cx="200" cy="150" rx="98" ry="118" fill="none" stroke="${ovalStroke}" stroke-width="3.2" stroke-dasharray="${ovalDash}"></ellipse>

      <!-- Eye-level Pitch Reference Line -->
      <line x1="112" y1="${angle.eyeLineY}" x2="288" y2="${angle.eyeLineY}" stroke="rgba(255,255,255,0.55)" stroke-width="1.5" stroke-dasharray="5 5"></line>
      <text x="118" y="${angle.eyeLineY - 5}" fill="rgba(255,255,255,0.75)" font-size="10" font-weight="700">MẮT</text>

      <!-- 3D Yaw Nose Axis Curve -->
      <path d="${angle.noseCurve}" fill="none" stroke="rgba(242, 255, 71, 0.72)" stroke-width="2" stroke-dasharray="4 4"></path>

      <!-- Target Nose Alignment Reticle -->
      <circle cx="${angle.targetX}" cy="${angle.targetY}" r="18" fill="rgba(242, 255, 71, 0.16)" stroke="${ovalStroke}" stroke-width="2.5"></circle>
      <circle cx="${angle.targetX}" cy="${angle.targetY}" r="4.5" fill="${ovalStroke}"></circle>

      <!-- Live Face Center Indicator (shown when camera active) -->
      ${
        mediaStream
          ? `<circle cx="${liveFaceDot.x}" cy="${liveFaceDot.y}" r="7" fill="${isAligned ? "#22c55e" : "#38bdf8"}" stroke="#ffffff" stroke-width="2"></circle>`
          : ""
      }
    `;
  }

  function updateGuideBanner() {
    const angle = ANGLES[activeAngleIndex] || ANGLES[0];
    const titleEl = document.getElementById("faceGuideTitle");
    const descEl = document.getElementById("faceGuideDesc");
    const iconEl = document.getElementById("faceGuideIcon");
    if (titleEl) titleEl.textContent = angle.detailTitle;
    if (descEl) descEl.textContent = angle.detailInstruction;
    if (iconEl) iconEl.innerHTML = icon(angle.faIcon);
  }

  function setTelemetryPill(id, text, state) {
    const el = document.getElementById(id);
    if (!el) return;
    el.className = `telemetry-pill ${state || ""}`;
    el.innerHTML = text;
  }

  function renderAngleSteps() {
    const grid = document.getElementById("faceAngleStepsGrid");
    const promptEl = document.getElementById("facePromptPill");
    const progressEl = document.getElementById("faceProgressText");
    const saveBtn = document.getElementById("faceSaveEnrollBtn");
    if (!grid) return;

    const capturedCount = Object.keys(capturedAngles).length;
    if (progressEl) {
      progressEl.textContent = `Tiến độ: ${capturedCount}/${ANGLES.length} góc đã chụp`;
    }
    if (promptEl) {
      const current = ANGLES[activeAngleIndex] || ANGLES[0];
      promptEl.textContent =
        capturedCount === ANGLES.length
          ? "Đã đủ 5 góc! Nhấn Lưu để kích hoạt Face ID"
          : `Bước ${activeAngleIndex + 1}/5: ${current.shortPrompt}`;
    }
    if (saveBtn) {
      saveBtn.disabled = capturedCount < ANGLES.length;
    }

    updateGuideBanner();
    renderHudOverlay(liveFaceDot.aligned);

    grid.innerHTML = ANGLES.map((angle, idx) => {
      const imgData = capturedAngles[angle.key];
      const isCurrent = idx === activeAngleIndex;
      return `
        <div class="angle-step-card ${isCurrent ? "current" : ""} ${imgData ? "captured" : ""}" data-angle-idx="${idx}">
          <div class="angle-thumb">
            ${imgData ? `<img src="${imgData}" alt="${angle.label}">` : icon(angle.faIcon)}
          </div>
          <div class="angle-step-name">${angle.label}</div>
        </div>
      `;
    }).join("");

    grid.querySelectorAll("[data-angle-idx]").forEach((card) => {
      card.addEventListener("click", () => {
        activeAngleIndex = parseInt(card.getAttribute("data-angle-idx"), 10);
        stableAlignedTicks = 0;
        renderAngleSteps();
      });
    });
  }

  function updateStatusUI(statusData) {
    const toggle = document.getElementById("faceAuthToggleInput");
    const badge = document.getElementById("faceStatusBadge");
    const desc = document.getElementById("faceStatusDesc");

    const enabled = Boolean(statusData.face_auth_enabled);
    const registered = Boolean(statusData.face_registered);
    const enrolledList = statusData.enrolled_angles || [];

    if (toggle) toggle.checked = enabled;
    if (badge) {
      badge.textContent = enabled ? "ĐANG BẬT" : registered ? "ĐANG TẮT" : "CHƯA ĐĂNG KÝ";
      badge.className = `pill-badge ${enabled ? "COLLECTED" : registered ? "OCCUPIED" : "REGISTERED"}`;
    }
    if (desc) {
      desc.textContent = registered
        ? `Đã đăng ký ${enrolledList.length}/5 góc khuôn mặt. Có thể mở tủ bằng khuôn mặt hoặc OTP.`
        : "Chưa có dữ liệu khuôn mặt. Hãy căn chỉnh và chụp đủ 5 góc độ bên dưới để kích hoạt.";
    }
  }

  function analyzeVideoFrame() {
    const video = document.getElementById("faceCameraVideo");
    const analysisCanvas = document.getElementById("faceAnalysisCanvas");
    const countdownEl = document.getElementById("faceCountdownBadge");
    const autoCaptureToggle = document.getElementById("faceAutoCaptureToggle");

    if (!video || !mediaStream || !analysisCanvas || video.videoWidth === 0) return;

    const w = 80;
    const h = 60;
    analysisCanvas.width = w;
    analysisCanvas.height = h;
    const ctx = analysisCanvas.getContext("2d", { willReadFrequently: true });

    // Mirror to match preview
    ctx.save();
    ctx.scale(-1, 1);
    ctx.drawImage(video, -w, 0, w, h);
    ctx.restore();

    const frame = ctx.getImageData(0, 0, w, h).data;

    // 1. Analyze brightness & weighted center inside oval region
    let sumLuma = 0;
    let ovalPixels = 0;
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
        ovalPixels++;

        // Skin/face prominence heuristic for centroid estimation
        const isSkinLike = r > 65 && g > 40 && b > 25 && r > g && r > b && Math.abs(r - g) > 10;
        const wFactor = isSkinLike ? 3.0 : luma > 75 ? 0.6 : 0.1;
        weightedX += x * wFactor;
        weightedY += y * wFactor;
        weightTotal += wFactor;

        if (prevSampleData) {
          motionDiff += Math.abs(luma - prevSampleData[y * w + x]);
        }
      }
    }

    // Store compact luma buffer for next stability check
    const curLumaBuf = new Uint8Array(w * h);
    for (let i = 0; i < w * h; i++) {
      const p = i * 4;
      curLumaBuf[i] = (0.299 * frame[p] + 0.587 * frame[p + 1] + 0.114 * frame[p + 2]) | 0;
    }
    prevSampleData = curLumaBuf;

    const avgLuma = ovalPixels > 0 ? sumLuma / ovalPixels : 0;
    const avgMotion = ovalPixels > 0 ? motionDiff / ovalPixels : 99;

    const cx = weightTotal > 0 ? (weightedX / weightTotal / w) * 400 : 200;
    const cy = weightTotal > 0 ? (weightedY / weightTotal / h) * 300 : 150;

    // Smooth indicator dot
    liveFaceDot.x = Math.round(liveFaceDot.x * 0.45 + cx * 0.55);
    liveFaceDot.y = Math.round(liveFaceDot.y * 0.45 + cy * 0.55);

    const lightOk = avgLuma >= 55 && avgLuma <= 225;
    const frameCentered = Math.abs(liveFaceDot.x - 200) < 62 && Math.abs(liveFaceDot.y - 150) < 58;
    const isStable = avgMotion < 12.5;
    const allGood = lightOk && frameCentered && isStable;
    liveFaceDot.aligned = allGood;

    // Update 3 live telemetry pills
    setTelemetryPill(
      "telLight",
      `${icon("sun")} ${avgLuma < 55 ? "Thiếu sáng" : avgLuma > 225 ? "Quá chói" : "Ánh sáng tốt"}`,
      lightOk ? "ok" : "warn"
    );
    setTelemetryPill(
      "telFrame",
      `${icon("crosshairs")} ${frameCentered ? "Khớp khung mặt" : "Đưa mặt vào giữa"}`,
      frameCentered ? "ok" : "warn"
    );
    setTelemetryPill(
      "telStable",
      `${icon("circle-check")} ${isStable ? "Đầu ổn định" : "Giữ yên đầu"}`,
      isStable ? "ok" : "warn"
    );

    renderHudOverlay(allGood);

    // Optional Auto-Capture Countdown when aligned & stable
    const autoOn = autoCaptureToggle && autoCaptureToggle.checked;
    const alreadyComplete = Object.keys(capturedAngles).length >= ANGLES.length;
    if (autoOn && allGood && !alreadyComplete) {
      stableAlignedTicks++;
      const remaining = Math.max(1, 4 - Math.ceil(stableAlignedTicks / 2));
      if (countdownEl) {
        countdownEl.style.display = "block";
        countdownEl.textContent = `Giữ nguyên... ${remaining}`;
      }
      if (stableAlignedTicks >= 7) {
        stableAlignedTicks = 0;
        if (countdownEl) countdownEl.style.display = "none";
        captureCurrentAngle();
      }
    } else {
      stableAlignedTicks = 0;
      if (countdownEl) countdownEl.style.display = "none";
    }
  }

  async function startCamera() {
    const video = document.getElementById("faceCameraVideo");
    const startBtn = document.getElementById("faceStartCameraBtn");
    if (!video) return;

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      window.SmartAuth.showToast("Trình duyệt không hỗ trợ Camera. Bạn có thể bấm Chụp Góc Này để dùng khung mẫu.", "error");
      return;
    }
    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } },
        audio: false,
      });
      video.srcObject = mediaStream;
      await video.play();
      if (startBtn) startBtn.innerHTML = `${icon("video")} Camera Đang Bật`;

      prevSampleData = null;
      stableAlignedTicks = 0;
      if (analyzerTimer) clearInterval(analyzerTimer);
      analyzerTimer = setInterval(analyzeVideoFrame, 180);

      window.SmartAuth.showToast("Đã bật Camera! Hãy căn mắt theo đường kẻ và đưa mũi vào vòng tâm ngắm.");
    } catch (err) {
      window.SmartAuth.showToast("Không thể truy cập Camera (kiểm tra quyền truy cập hoặc HTTPS).", "error");
    }
  }

  function stopCamera() {
    if (analyzerTimer) {
      clearInterval(analyzerTimer);
      analyzerTimer = null;
    }
    if (mediaStream) {
      mediaStream.getTracks().forEach((t) => t.stop());
      mediaStream = null;
    }
    const video = document.getElementById("faceCameraVideo");
    if (video) video.srcObject = null;
    const startBtn = document.getElementById("faceStartCameraBtn");
    if (startBtn) startBtn.innerHTML = `${icon("video")} Bật Camera`;
    const countdownEl = document.getElementById("faceCountdownBadge");
    if (countdownEl) countdownEl.style.display = "none";
    renderHudOverlay(false);
  }

  function captureCurrentAngle() {
    const video = document.getElementById("faceCameraVideo");
    const canvas = document.getElementById("faceCaptureCanvas");
    if (!canvas) return;

    const angle = ANGLES[activeAngleIndex];
    const ctx = canvas.getContext("2d");
    canvas.width = 240;
    canvas.height = 180;

    if (video && mediaStream && video.videoWidth > 0) {
      ctx.save();
      ctx.scale(-1, 1);
      ctx.drawImage(video, -canvas.width, 0, canvas.width, canvas.height);
      ctx.restore();
    } else {
      ctx.fillStyle = "#181816";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = "#f2ff47";
      ctx.font = "bold 16px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(`FACE ANGLE: ${angle.key.toUpperCase()}`, canvas.width / 2, canvas.height / 2);
    }

    capturedAngles[angle.key] = canvas.toDataURL("image/jpeg", 0.68);
    window.SmartAuth.showToast(`Đã chụp xong góc: ${angle.label}`);

    const nextMissing = ANGLES.findIndex((a) => !capturedAngles[a.key]);
    if (nextMissing !== -1) {
      activeAngleIndex = nextMissing;
    }
    stableAlignedTicks = 0;
    renderAngleSteps();
  }

  async function saveEnrollment() {
    if (!currentUser) return;
    const saveBtn = document.getElementById("faceSaveEnrollBtn");
    if (saveBtn) {
      saveBtn.disabled = true;
      saveBtn.textContent = "Đang lưu dữ liệu 5 góc...";
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
      window.SmartAuth.showToast(res.message || "Đăng ký Face ID 5 góc thành công!");
    } catch (err) {
      window.SmartAuth.showToast(err.message || "Lỗi khi lưu dữ liệu khuôn mặt.", "error");
    } finally {
      if (saveBtn) {
        saveBtn.disabled = Object.keys(capturedAngles).length < ANGLES.length;
        saveBtn.innerHTML = `${icon("circle-check")} Lưu & Kích Hoạt Face ID`;
      }
    }
  }

  async function handleToggleChange(e) {
    if (!currentUser) return;
    const enabled = e.target.checked;
    try {
      const res = await window.SmartApi.post("/auth/face/toggle", {
        user_id: currentUser.id,
        enabled,
      });
      updateStatusUI(res);
      window.SmartAuth.updateSessionUser({ face_auth_enabled: res.face_auth_enabled });
      window.SmartAuth.showToast(res.message);
    } catch (err) {
      e.target.checked = !enabled;
      window.SmartAuth.showToast(err.message || "Không thể thay đổi trạng thái Face ID.", "error");
    }
  }

  async function refreshStatus() {
    if (!currentUser) return;
    try {
      const res = await window.SmartApi.get(`/auth/face/status/${currentUser.id}`);
      updateStatusUI(res);
    } catch (_) {}
  }

  function init(user) {
    currentUser = user;
    renderAngleSteps();
    refreshStatus();

    const toggle = document.getElementById("faceAuthToggleInput");
    const startBtn = document.getElementById("faceStartCameraBtn");
    const captureBtn = document.getElementById("faceCaptureAngleBtn");
    const resetBtn = document.getElementById("faceResetAnglesBtn");
    const saveBtn = document.getElementById("faceSaveEnrollBtn");

    if (toggle) toggle.addEventListener("change", handleToggleChange);
    if (startBtn) startBtn.addEventListener("click", startCamera);
    if (captureBtn) captureBtn.addEventListener("click", captureCurrentAngle);
    if (resetBtn) {
      resetBtn.addEventListener("click", () => {
        capturedAngles = {};
        activeAngleIndex = 0;
        stableAlignedTicks = 0;
        renderAngleSteps();
      });
    }
    if (saveBtn) saveBtn.addEventListener("click", saveEnrollment);
  }

  return { init, stopCamera, refreshStatus };
})();
