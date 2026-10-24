import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Vite's CORS middleware runs before the proxy and answers every OPTIONS with an empty 204,
    // which hides the admin console's form metadata (OPTIONS /api/v1/admin/<resource>). The app is same-origin.
    cors: false,
    // Dev proxy to the Django API (docker compose publishes it on WEB_PORT, default 9009).
    proxy: {
      "/api": { target: process.env.VITE_PROXY_TARGET || "http://localhost:9009", changeOrigin: true },
      "/media": { target: process.env.VITE_PROXY_TARGET || "http://localhost:9009", changeOrigin: true },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.js"],
    globals: true,
    testTimeout: 20000,
    // Tests cover the "not configured" state regardless of a developer's .env.local.
    env: { VITE_GOOGLE_CLIENT_ID: "" },
  },
});
