import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, list, setCsrfToken } from "./api";
describe("Atlas API client contracts", () => {
  const fetchMock = vi.fn();
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("window", { dispatchEvent: vi.fn() });
    vi.stubGlobal("document", { cookie: "csrftoken=cookie-value" });
    setCsrfToken("");
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    fetchMock.mockReset();
  });
  it("canonicalizes Django URLs before query parameters", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ results: [] }), {
        headers: { "Content-Type": "application/json" },
      }),
    );
    await api("/work?mine=true&search=a%20b");
    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/v1/work/?mine=true&search=a%20b",
    );
  });
  it("does not duplicate a canonical trailing slash", async () => {
    fetchMock.mockResolvedValue(
      new Response("{}", { headers: { "Content-Type": "application/json" } }),
    );
    await api("/auth/me/");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/auth/me/");
  });
  it("uses session cookies, CSRF and a unique request id on mutation", async () => {
    fetchMock.mockResolvedValue(
      new Response("{}", { headers: { "Content-Type": "application/json" } }),
    );
    setCsrfToken("active-session-token");
    await api("/work", {
      method: "POST",
      body: { title: "Kaynak incelemesi" },
    });
    const request = fetchMock.mock.calls[0][1];
    expect(request.credentials).toBe("same-origin");
    expect(request.headers.get("X-CSRFToken")).toBe("active-session-token");
    expect(request.headers.get("X-Request-ID")).toMatch(/^[0-9a-f-]{36}$/);
    expect(JSON.parse(request.body)).toEqual({ title: "Kaynak incelemesi" });
  });
  it("uses rotated csrf token returned by the server", async () => {
    fetchMock
      .mockResolvedValueOnce(
        new Response('{"csrf_token":"rotated"}', {
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response("{}", { headers: { "Content-Type": "application/json" } }),
      );
    await api("/auth/login", { method: "POST", body: {} });
    await api("/auth/logout", { method: "POST" });
    expect(fetchMock.mock.calls[1][1].headers.get("X-CSRFToken")).toBe(
      "rotated",
    );
  });
  it("preserves human-readable integration test failures", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        '{"status":"failure","message":"TLS doğrulaması başarısız"}',
        { status: 400, headers: { "Content-Type": "application/json" } },
      ),
    );
    await expect(
      api("/admin/integrations/ldap/test", { method: "POST" }),
    ).rejects.toThrow("TLS doğrulaması başarısız");
  });
  it("turns field validation errors into actionable feedback", async () => {
    fetchMock.mockResolvedValue(
      new Response('{"pm_id":["Etkin proje yöneticisi bulunamadı."]}', {
        status: 400,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await expect(api("/projects", { method: "POST" })).rejects.toThrow(
      "pm_id: Etkin proje yöneticisi bulunamadı.",
    );
  });
  it("does not display a raw server traceback as user feedback", async () => {
    fetchMock.mockResolvedValue(
      new Response("<html>Internal traceback with sensitive text</html>", {
        status: 500,
        headers: { "Content-Type": "text/html" },
      }),
    );
    await expect(api("/dashboard")).rejects.toThrow(
      "İşlem tamamlanamadı (500).",
    );
  });
  it("recovers list shape safely when optional results are absent", () => {
    expect(list(undefined)).toEqual([]);
    expect(list({ results: null })).toEqual([]);
    expect(list({ results: [{ id: "a" }] })).toEqual([{ id: "a" }]);
    expect(list([{ id: "b" }])).toEqual([{ id: "b" }]);
  });
  it("translates offline failures into a recoverable API error", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(api("/dashboard")).rejects.toMatchObject({
      name: "ApiError",
      status: 0,
    });
  });
});
