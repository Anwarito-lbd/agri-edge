import type { NextConfig } from "next";

import { BASEMAP_HOST } from "./src/lib/basemap";

/**
 * Security headers on every response.
 *
 * The CSP keeps 'unsafe-inline' for scripts and styles because the App Router
 * inlines its bootstrap and Tailwind emits inline styles; moving to nonces is
 * the next step. What it does pin down: nothing loads from anywhere but this
 * origin and the map tile server, nothing can frame the app (so no
 * clickjacking of the approve buttons), and forms post only here.
 */
const isDev = process.env.NODE_ENV !== "production";
const TILES = BASEMAP_HOST;

const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  `img-src 'self' data: blob: ${TILES}`,
  "font-src 'self' data:",
  `connect-src 'self'${isDev ? " ws: wss:" : ""}`,
  "worker-src 'self'",
  "manifest-src 'self'",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

export const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(self)" },
];

const nextConfig: NextConfig = {
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
