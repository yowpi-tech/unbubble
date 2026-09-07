import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Local-only tool: no telemetry-sensitive headers, no CSP (the audit reports are
  // self-contained HTML rendered inside an <iframe> from the same origin).
  reactStrictMode: true,
  serverExternalPackages: [],
};

export default nextConfig;
