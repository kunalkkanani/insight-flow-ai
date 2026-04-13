import type { NextConfig } from "next";

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,

  // Proxy light JSON/REST calls through Next.js.
  // File uploads and SSE streams bypass this proxy and go direct to the
  // backend (see api.ts) — large request bodies and long-lived connections
  // don't belong in a rewrite proxy.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND_URL}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
