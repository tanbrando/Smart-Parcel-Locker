/**
 * Core HTTP API Client Module
 * Centralizes REST API calls and attaches Bearer auth token when available.
 */
window.SmartApi = (() => {
  const API_BASE = "/api/v1";

  function getAuthHeaders(extra = {}) {
    const headers = { ...extra };
    try {
      const raw = localStorage.getItem("smartlocker_session");
      if (raw) {
        const session = JSON.parse(raw);
        if (session && session.token) {
          headers["Authorization"] = `Bearer ${session.token}`;
        }
      }
    } catch (_) {
      // ignore storage errors
    }
    return headers;
  }

  async function request(path, options = {}) {
    const isFormData = options.body instanceof FormData;
    const baseHeaders = isFormData ? {} : { "Content-Type": "application/json" };
    const headers = getAuthHeaders({ ...baseHeaders, ...(options.headers || {}) });

    const res = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
    });

    const contentType = res.headers.get("content-type") || "";
    const data = contentType.includes("application/json") ? await res.json() : await res.text();

    if (!res.ok) {
      const message =
        (data && typeof data === "object" && (data.detail || data.message)) ||
        `Yêu cầu thất bại (HTTP ${res.status})`;
      const error = new Error(message);
      error.status = res.status;
      error.data = data;
      throw error;
    }
    return data;
  }

  return {
    API_BASE,
    get: (path) => request(path, { method: "GET" }),
    post: (path, body) =>
      request(path, {
        method: "POST",
        body: body instanceof FormData ? body : JSON.stringify(body),
      }),
    patch: (path, body) =>
      request(path, {
        method: "PATCH",
        body: body ? JSON.stringify(body) : undefined,
      }),
  };
})();
