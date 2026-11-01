import { defineConfig, devices } from "@playwright/test";

/**
 * The python fixture binds an ephemeral port and announces it on stdout, so
 * the harness cannot be a static `webServer` entry. `global-setup.ts` builds
 * the embed bundle, spawns the fixture, the CORS shim, the `packages/app`
 * two-origin server (we use its sandbox origin :8081) and the embed static
 * server (:8090); `global-teardown.ts` stops all of them.
 */
export default defineConfig({
  testDir: ".",
  testMatch: /.*\.spec\.ts/,
  workers: 1,
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  use: { baseURL: "http://localhost:8090" },
  globalSetup: "./global-setup.ts",
  globalTeardown: "./global-teardown.ts",
  reporter: [["list"], ["html", { open: "never", outputFolder: "../playwright-report" }]],
  outputDir: "../test-results",
});
