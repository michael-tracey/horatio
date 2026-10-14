import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The API runs on :8000 in development (`uv run uvicorn horatio.app:app --reload`).
// Proxying /api keeps the app and API on one origin, which sign-in relies on (ADR 0005).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: { "/api": "http://localhost:8000" },
  },
  test: {
    environment: "jsdom",
  },
});
