import { defineConfig } from "vite";

import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import tsConfigPaths from "vite-tsconfig-paths";

// Keep in step with the backend's PORT. Defaults to 5001, not 5000, because
// macOS has claimed 5000 since Monterey: AirPlay Receiver answers there with a
// 403, which reaches the browser as "Request failed (403)" on upload and looks
// exactly like a broken backend. Override with API_PORT if you moved it.
// Docker is unaffected — nginx talks to model:5000 on the container network.
const API_PORT = process.env.API_PORT ?? "5001";

// Plain Vite + React single-page app (routing handled by react-router-dom).
export default defineConfig({
  plugins: [react(), tailwindcss(), tsConfigPaths()],
  server: {
    port: 5173,
    // Forward API calls to the FastAPI backend during local development so the
    // browser sees a single origin (mirrors what nginx does in production).
    proxy: {
      "/api": {
        target: `http://localhost:${API_PORT}`,
        changeOrigin: true,
        // The multiplayer game connects to /api/game/ws, so the dev proxy has to
        // forward the WebSocket upgrade too (nginx already does in production).
        ws: true,
      },
      // Dog photos. In production nginx serves these off the `dogdata` volume;
      // in dev the backend static-mounts the same directory, so ingesting once
      // locally is enough to see real dogs at `npm run dev`.
      "/dogs": {
        target: `http://localhost:${API_PORT}`,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
  },
});
