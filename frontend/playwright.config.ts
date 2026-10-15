import { defineConfig, devices } from "@playwright/test";

// Runs against a backend that serves the built frontend. Locally, ../e2e-local.sh
// does it all against a fresh database of its own, leaving the dev one alone.
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
