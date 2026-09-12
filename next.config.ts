import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  experimental: {
    serverActions: {
      allowedOrigins: ["fads.aindoori.com"],
      bodySizeLimit: "12mb",
    },
  },
};

export default nextConfig;
