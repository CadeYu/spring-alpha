import type { NextConfig } from "next";

const backendUrl = process.env.BACKEND_URL || 'http://127.0.0.1:8081';

const nextConfig: NextConfig = {
  // standalone only for Docker, Vercel handles this automatically
  ...(process.env.STANDALONE === 'true' ? { output: 'standalone' as const } : {}),
  async rewrites() {
    return [
      {
        source: '/api/java/:path*',
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
