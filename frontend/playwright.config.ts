import { defineConfig, devices } from "@playwright/test";

// Runs against a backend that serves the built frontend. Locally, ../e2e-local.sh
// does it all against a fresh database of its own, leaving the dev one alone.
const baseURL = process.env.HORATIO_E2E_URL ?? "http://localhost:8766";

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
    baseURL,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    // The service worker that keeps the app for offline use (#502) would keep one
    // test's build and answers for the next. Only the offline tests allow it.
    serviceWorkers: "block",
    // Each browser has already answered whether to keep a person's characters on it
    // (online only), so the question doesn't stand in front of every test; the
    // offline tests start without it.
    storageState: { cookies: [], origins: [{ origin: new URL(baseURL).origin, localStorage: [{ name: "horatio.offline.asked", value: "1" }] }] },
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
});
