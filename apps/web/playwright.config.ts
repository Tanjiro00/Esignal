import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

const repositoryRoot = path.resolve(__dirname, "../..");
const apiPort = process.env.E2E_API_PORT ?? "8000";
const webPort = process.env.E2E_WEB_PORT ?? "3000";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${webPort}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    viewport: { width: 1600, height: 1000 },
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command: "uv run python scripts/start_e2e.py",
      cwd: repositoryRoot,
      env: {
        PORT: apiPort,
        WEB_ORIGIN: `http://127.0.0.1:${webPort}`,
      },
      port: Number(apiPort),
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `npm run dev --workspace @earlysignal/web -- --hostname 127.0.0.1 --port ${webPort}`,
      cwd: repositoryRoot,
      env: {
        NEXT_PUBLIC_API_URL: `http://127.0.0.1:${apiPort}/api/v1`,
      },
      port: Number(webPort),
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
