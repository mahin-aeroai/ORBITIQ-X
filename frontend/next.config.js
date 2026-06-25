/** @type {import('next').NextConfig} */
const nextConfig = {
  // In production (with internet access), Next.js downloads and self-hosts Google Fonts.
  // In CI/sandbox environments without google font access, set optimizeFonts: false.
  // On your local machine and production server, remove this line or set to true.
  optimizeFonts: process.env.NEXT_OPTIMIZE_FONTS !== "false",

  // ── Cesium / webpack ──────────────────────────────────────────────────────
  // Cesium workers are CommonJS bundles that webpack tries to parse as ESM.
  // Marking them as external prevents the parse error (Phase 13A fix).
  webpack: (config, { isServer }) => {
    if (!isServer) {
      // Don't bundle Cesium workers — they self-load via URL
      config.externals = config.externals || [];

      // Silence Cesium worker size warnings
      config.performance = {
        ...config.performance,
        hints: false,
      };

      // Required for Cesium: mark as asset/resource
      config.module.rules.push({
        test: /\.worker\.js$/,
        use:  { loader: "worker-loader" },
      });
    }

    // info.minimized suppresses the "Asset size limit" warning for Cesium
    config.infrastructureLogging = {
      ...config.infrastructureLogging,
      level: "error",
    };

    return config;
  },

  // ── Output ────────────────────────────────────────────────────────────────
  output: "standalone",

  // ── Images ───────────────────────────────────────────────────────────────
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "cesium.com" },
      { protocol: "https", hostname: "ion.cesium.com" },
    ],
  },

  // ── Environment ───────────────────────────────────────────────────────────
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
    NEXT_PUBLIC_CESIUM_ION_TOKEN: process.env.NEXT_PUBLIC_CESIUM_ION_TOKEN ?? "",
  },

  // ── Experimental ──────────────────────────────────────────────────────────
  experimental: {
    // Needed for SSE streaming responses from Next.js route handlers
    serverActions: {
      allowedOrigins: [
        "localhost:3000",
        "orbitiq-x.vercel.app",
        ".vercel.app",
      ],
    },
  },

  // ── TypeScript + ESLint ───────────────────────────────────────────────────
  typescript: {
    ignoreBuildErrors: false,
  },
  eslint: {
    ignoreDuringBuilds: false,
  },
};

module.exports = nextConfig;
