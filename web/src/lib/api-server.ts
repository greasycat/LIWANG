import "server-only";

import { cookies } from "next/headers";

import { ApiError, parseError } from "./api";

const INTERNAL_BASE =
  process.env.LIWANG_API_URL || "http://127.0.0.1:8000";

/** Server-side fetch — forwards the incoming session cookie to FastAPI. */
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

export { ApiError };
