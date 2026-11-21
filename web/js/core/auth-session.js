/**
 * Core Authentication Session & Toast Notification Module
 * Handles login persistence, role guards (USER vs ADMIN), and global toast feedback.
 */
window.SmartAuth = (() => {
  const SESSION_KEY = "smartlocker_session";

  function getSession() {
    try {
      const raw = localStorage.getItem(SESSION_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (!parsed || !parsed.user || !parsed.token) return null;
      return parsed;
    } catch (_) {
      return null;
    }
  }

  function saveSession(loginResponse) {
    const session = {
      token: loginResponse.token,
      user: loginResponse.user,
      savedAt: Date.now(),
    };
    localStorage.setItem(SESSION_KEY, JSON.stringify(session));
    return session;
  }

  function updateSessionUser(updatedUser) {
    const current = getSession();
    if (!current) return;
    current.user = { ...current.user, ...updatedUser };
    localStorage.setItem(SESSION_KEY, JSON.stringify(current));
  }

  function clearSession() {
    localStorage.removeItem(SESSION_KEY);
  }

  function logout() {
    clearSession();
    window.location.href = "/login";
  }

  /**
   * Ensures the visitor has an active session matching the expected role.
   * Redirects to /login if unauthenticated, or to the right home if wrong role.
   */
  function requireRole(expectedRole) {
    const session = getSession();
    if (!session) {
      window.location.href = "/login";
      return null;
    }
    const role = (session.user.role || "USER").toUpperCase();
    if (expectedRole && role !== expectedRole.toUpperCase()) {
      window.location.href = role === "ADMIN" ? "/" : "/portal";
      return null;
    }
    return session;
  }

  function showToast(message, type = "success", durationMs = 3600) {
    let container = document.getElementById("globalToastContainer");
    if (!container) {
      container = document.createElement("div");
      container.id = "globalToastContainer";
      container.className = "toast-container";
      document.body.appendChild(container);
    }
    const item = document.createElement("div");
    item.className = `toast-item ${type}`;
    item.innerHTML = `<span>${message}</span>`;
    container.appendChild(item);

    setTimeout(() => {
      item.style.opacity = "0";
      item.style.transition = "opacity 0.25s ease";
      setTimeout(() => item.remove(), 260);
    }, durationMs);
  }

  return {
    getSession,
    saveSession,
    updateSessionUser,
    clearSession,
    logout,
    requireRole,
    showToast,
  };
})();
