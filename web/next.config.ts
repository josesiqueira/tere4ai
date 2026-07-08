import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // thin, read-only demo UI (docs/architecture.md Section 9); no API routes
  output: "standalone",
};

export default nextConfig;
