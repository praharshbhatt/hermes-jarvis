import type { NextConfig } from "next";

// `npm run build` produces a fully static site in out/ (no Node at runtime: the Python service serves it).
// `npm run dev` runs the dev server and proxies /api and /healthz to a running service (scripts/admin_demo.py, port 8680).
const dev = process.env.NODE_ENV !== "production";
const api = process.env.HJ_API ?? "http://127.0.0.1:8680";

const config: NextConfig = {
  ...(dev ? {} : { output: "export" as const }),
  trailingSlash: true,
  images: { unoptimized: true },
  poweredByHeader: false,
  reactStrictMode: true,
  ...(dev
    ? {
        async rewrites() {
          return [
            { source: "/api/:path*", destination: `${api}/api/:path*` },
            { source: "/healthz", destination: `${api}/healthz` },
          ];
        },
      }
    : {}),
};

export default config;
