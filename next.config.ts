import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  experimental: {
    serverActions: {
      allowedOrigins: ["fads.aindoori.com"],
      bodySizeLimit: "12mb",
    },
  },
  async rewrites() {
    return [
      { source: "/voice", destination: "http://127.0.0.1:8810/voice" },
      { source: "/voice/:path*", destination: "http://127.0.0.1:8810/voice/:path*" },
      { source: "/voice-api/:path*", destination: "http://127.0.0.1:8811/api/:path*" },
    ];
  },
};

export default nextConfig;
