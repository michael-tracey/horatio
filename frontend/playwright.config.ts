import { defineConfig, devices } from "@playwright/test";

// Runs against a backend that serves the built frontend. Locally, ../e2e-local.sh
// does it all against a fresh database of its own, leaving the dev one alone.
export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  // One API server serves every worker, and judging a cart is slow work for it.
  // Two workers, as on CI's runners, keep its answers inside the suite's waits;
  // the default of half the cores floods it on a bigger machine.
  workers: 2,
  // Each test a unit of its own, so CI's --shard can split a file between runners.
  fullyParallel: true,
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
