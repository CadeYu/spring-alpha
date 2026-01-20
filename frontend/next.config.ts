import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  async rewrites() {
    return [
      {
        source: '/api/java/:path*',
        destination: 'http://127.0.0.1:8081/api/:path*',
      },
    ];
  },
};

export default nextConfig;
