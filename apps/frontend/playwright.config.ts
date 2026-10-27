import {defineConfig} from "@playwright/test";
export default defineConfig({testDir: "./e2e", testMatch: process.env.E2E_SUITE === "bank" ? "bank.spec.ts" : process.env.E2E_SUITE === "retry" ? "retry.spec.ts" : ["practice.spec.ts", "client.spec.ts"], workers: 1, retries: 0, timeout: 45000,
  reporter: [["list"]], use: {baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3100", headless: true, trace: "off", screenshot: "only-on-failure"}});
