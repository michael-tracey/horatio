import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Proxying /api to the API keeps the app and API on one origin, which sign-in
// relies on (ADR 0005). The API is on :8000 unless HORATIO_API_PORT says otherwise.
const apiPort = process.env.HORATIO_API_PORT ?? "8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: { "/api": `http://localhost:${apiPort}` },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
