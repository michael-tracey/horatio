import { defineConfig, devices } from "@playwright/test";

// Runs against a backend that serves the built frontend, for example:
//   HORATIO_COOKIE_SECURE=false HORATIO_FRONTEND_DIST=$PWD/dist uv run uvicorn horatio.app:app --port 8766
export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  use: {
    baseURL: process.env.HORATIO_E2E_URL ?? "http://localhost:8766",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
});
