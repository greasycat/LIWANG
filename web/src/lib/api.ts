/**
 * Shared API plumbing — error type + client fetcher.
 *
 * Server-only helpers (those that read cookies via `next/headers`) live in
 * `./api-server` so client bundles don't drag the server-only module in.
 */

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

export async function parseError(res: Response): Promise<ApiError> {
  let detail: unknown = res.statusText;
  try {
    const j = await res.json();
    detail = j?.detail ?? j;
  } catch {
    /* ignore */
  }
  return new ApiError(res.status, detail);
}

/** Client-side fetch — relies on browser cookie + Next.js rewrite proxy. */
export async function apiClient<T = unknown>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const url = path.startsWith("/api") ? path : `/api${path}`;
  const res = await fetch(url, {
    credentials: "same-origin",
    ...init,
    headers: {
      ...(init?.body && !(init.body instanceof FormData)
        ? { "content-type": "application/json" }
        : {}),
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return (await res.json()) as T;
  return undefined as T;
}
