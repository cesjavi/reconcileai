import path from "node:path";
import { defineConfig } from "@playwright/test";

// Starts the API (fresh SQLite, MOCK inference, Evolus disabled) and the built web app.
// Set E2E_BASE_URL to test an already running stack (e.g. docker compose) instead.
// The web app must be built with NEXT_PUBLIC_API_URL=http://localhost:8100.
const external = process.env.E2E_BASE_URL;
const root = path.resolve(__dirname, "..");
const py = path.join(root, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const pythonPath = ["apps/api", "services/reconciliation", "services/inference", "services/evolus"]
  .map((p) => path.join(root, p)).join(path.delimiter);

export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  reporter: [["list"], ["json", { outputFile: "test-results/e2e.json" }]],
  use: { baseURL: external ?? "http://localhost:3100" },
  webServer: external ? undefined : [
    {
      command: `node -e "try{require('fs').rmSync('e2e.db')}catch(e){}" && "${py}" -m uvicorn app.main:app --port 8100`,
      cwd: path.join(root, "apps/api"),
      url: "http://localhost:8100/health",
      env: {
        DATABASE_URL: "sqlite:///./e2e.db", DEMO_DIR: path.join(root, "demo"),
        CORS_ORIGINS: "http://localhost:3100", PYTHONPATH: pythonPath,
        INFERENCE_PROVIDER: "mock", EVOLUS_MODE: "disabled",
      },
      reuseExistingServer: false,
    },
    {
      command: "npx next start -p 3100",
      cwd: path.join(root, "apps/web"),
      url: "http://localhost:3100",
      reuseExistingServer: !process.env.CI,
    },
  ],
});
