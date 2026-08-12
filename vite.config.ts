import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import tsConfigPaths from "vite-tsconfig-paths";

// Plain Vite + React single-page app (routing handled by react-router-dom).
export default defineConfig({
  plugins: [react(), tailwindcss(), tsConfigPaths()],
  server: {
    port: 5173,
    // Forward API calls to the FastAPI backend during local development so the
    // browser sees a single origin (mirrors what nginx does in production).
    proxy: {
      "/api": {
        target: "http://localhost:5000",
        changeOrigin: true,
        // The multiplayer game connects to /api/game/ws, so the dev proxy has to
        // forward the WebSocket upgrade too (nginx already does in production).
        ws: true,
      },
    },
  },
  build: {
    outDir: "dist",
  },
});
