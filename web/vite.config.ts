import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.HELIX_API_PROXY_TARGET ?? "http://localhost:8080",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
        headers: process.env.HELIX_API_KEY
          ? { "X-API-Key": process.env.HELIX_API_KEY }
          : undefined,
      },
    },
  },
});
