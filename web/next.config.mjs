/** @type {import('next').NextConfig} */
const API_TARGET = process.env.LIWANG_API_URL || "http://127.0.0.1:8000";

const nextConfig = {
  reactStrictMode: true,
  // Proxy /api/* and /healthz to the FastAPI backend so the session cookie
  // remains same-origin (no CORS, no SameSite headaches).
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API_TARGET}/api/:path*` },
      { source: "/healthz", destination: `${API_TARGET}/healthz` },
    ];
  },
};

export default nextConfig;
