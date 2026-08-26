import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwind from "@tailwindcss/vite";
import path from "node:path";

// In dev the panel runs on Vite (1420, the port Tauri expects) and proxies /api and
// /ws to the Python server on 8787. In production — served by FastAPI or wrapped in
// Tauri — the bundle sits behind the same origin as the API, so both paths are hit
// directly and there is no CORS surface at all.
export default defineConfig({
  plugins: [react(), tailwind()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  server: {
    port: 1420,
    strictPort: true,
    proxy: {
      "/api": { target: "http://127.0.0.1:8787", changeOrigin: true },
      "/ws": { target: "ws://127.0.0.1:8787", ws: true, changeOrigin: true },
    },
  },
  // FastAPI serves dist/ in production and Tauri bundles it.
  build: { target: "es2021", outDir: "dist", emptyOutDir: true, sourcemap: false },
});
