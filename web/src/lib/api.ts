/**
 * API helpers.
 *
 * - In Server Components: call `apiServer(path, init)`. It forwards the
 *   incoming session cookie to FastAPI (running behind the rewrite proxy).
 * - In Client Components: call `apiClient(path, init)`. Cookie is attached
 *   automatically by the browser since requests stay same-origin.
 */
import { cookies } from "next/headers";

const INTERNAL_BASE =
  process.env.LIWANG_API_URL || "http://127.0.0.1:8000";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

async function parseError(res: Response): Promise<ApiError> {
  let detail: unknown = res.statusText;
  try {
    const j = await res.json();
    detail = j?.detail ?? j;
  } catch {
    /* ignore */
  }
  return new ApiError(res.status, detail);
}

/** Server-side fetch — forwards session cookie. */
export async function apiServer<T = unknown>(
  path: string,
  init?: RequestInit & { allowError?: boolean },
): Promise<T> {
  const jar = await cookies();
  const cookieHeader = jar
    .getAll()
    .map((c) => `${c.name}=${c.value}`)
    .join("; ");

  const url = `${INTERNAL_BASE}${path.startsWith("/api") ? path : `/api${path}`}`;
  const res = await fetch(url, {
    ...init,
    headers: {
      ...(init?.headers || {}),
      ...(cookieHeader ? { cookie: cookieHeader } : {}),
    },
    cache: "no-store",
  });
  if (!res.ok && !init?.allowError) {
    throw await parseError(res);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
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
