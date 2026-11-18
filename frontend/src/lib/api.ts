import { useCallback, useEffect, useRef, useState } from "react";
export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}
export function list<T = any>(value: any): T[] {
  return Array.isArray(value)
    ? value
    : Array.isArray(value?.results)
      ? value.results
      : [];
}
let csrfToken = "";
export function setCsrfToken(value: string) {
  csrfToken = value;
}
function csrfCookie() {
  return (
    document.cookie
      .split("; ")
      .find((item) => item.startsWith("onecs_csrftoken="))
      ?.split("=")
      .slice(1)
      .join("=") ||
    document.cookie
      .split("; ")
      .find((item) => item.startsWith("csrftoken="))
      ?.split("=")
      .slice(1)
      .join("=") ||
    ""
  );
}
export async function api<T = any>(
  path: string,
  options: Omit<RequestInit, "body"> & { body?: unknown } = {},
): Promise<T> {
  const method = (options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers);
  const multipart = options.body instanceof FormData;
  headers.set("Accept", "application/json");
  if (options.body !== undefined && !multipart)
    headers.set("Content-Type", "application/json");
  if (multipart) headers.delete("Content-Type");
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    headers.set("X-CSRFToken", csrfToken || decodeURIComponent(csrfCookie()));
    if (!headers.has("X-Request-ID"))
      headers.set("X-Request-ID", crypto.randomUUID());
  }
  let response: Response;
  const [pathname, search = ""] = path.split("?");
  const normalized =
    `${pathname.startsWith("/") ? pathname : `/${pathname}`}`.replace(
      /\/+$/,
      "",
    ) + "/";
  try {
    response = await fetch(
      `/api/v1${normalized}${search ? `?${search}` : ""}`,
      {
        ...options,
        method,
        headers,
        body:
          options.body === undefined
            ? undefined
            : multipart
              ? (options.body as FormData)
              : JSON.stringify(options.body),
        credentials: "same-origin",
      },
    );
  } catch {
    throw new ApiError(
      "Sunucuya ulaşılamıyor. Bağlantınızı kontrol edip yeniden deneyin.",
      0,
    );
  }
  let body: any = null;
  const contentType = response.headers.get("content-type") || "";
  if (response.status !== 204) {
    if (contentType.includes("json")) body = await response.json();
    else body = await response.text();
  }
  if (!response.ok) {
    if (response.status === 401)
      window.dispatchEvent(new CustomEvent("onecs:session-expired"));
    throw new ApiError(
      typeof body?.detail === "string"
        ? body.detail
        : typeof body?.error === "string"
          ? body.error
          : typeof body?.message === "string"
            ? body.message
            : body && typeof body === "object"
              ? Object.entries(body)
                  .slice(0, 4)
                  .map(
                    ([key, value]) =>
                      `${key}: ${Array.isArray(value) ? value.join(", ") : String(value)}`,
                  )
                  .join(" · ")
              : response.status === 403
                ? "Bu işlem için yetkiniz bulunmuyor."
                : response.status === 409
                  ? "Kayıt değişti. Sayfayı yenileyip tekrar deneyin."
                  : `İşlem tamamlanamadı (${response.status}).`,
      response.status,
      body?.code,
    );
  }
  if (body?.csrf_token) setCsrfToken(body.csrf_token);
  return body as T;
}
export function useResource<T = any>(
  path: string | null,
  fallback?: T,
  interval = 20000,
) {
  const [data, setData] = useState<T | undefined>(fallback);
  const priorPath = useRef(path);
  const [loading, setLoading] = useState(!!path);
  const [error, setError] = useState("");
  const [nonce, setNonce] = useState(0);
  const refresh = useCallback(() => setNonce((n) => n + 1), []);
  useEffect(() => {
    if (priorPath.current !== path) {
      setData(fallback);
      setError("");
      priorPath.current = path;
    }
    if (!path) {
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    let first = true;
    let inFlight = false;
    const load = async () => {
      if (inFlight) return;
      inFlight = true;
      if (first) setLoading(true);
      try {
        const next = await api<T>(path, { signal: controller.signal });
        if (!controller.signal.aborted) {
          setData(next);
          setError("");
        }
      } catch (e) {
        if (!controller.signal.aborted) {
          if (e instanceof ApiError && [401, 403, 404].includes(e.status))
            setData(undefined);
          setError(e instanceof Error ? e.message : "Veri alınamadı.");
        }
      } finally {
        inFlight = false;
        if (!controller.signal.aborted) {
          setLoading(false);
          first = false;
        }
      }
    };
    void load();
    const timer = interval ? window.setInterval(load, interval) : undefined;
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [path, nonce, interval]);
  return { data, loading, error, refresh };
}
export function personName(value: any) {
  return typeof value === "string"
    ? value
    : value?.display_name || value?.username || "Atanmamış";
}
export function date(value?: string, withTime = false) {
  if (!value) return "Tarih yok";
  const d = new Date(value);
  return Number.isNaN(d.getTime())
    ? value
    : new Intl.DateTimeFormat("tr-TR", {
        day: "numeric",
        month: "short",
        ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
      }).format(d);
}
