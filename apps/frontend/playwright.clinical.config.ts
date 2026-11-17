import {defineConfig} from "@playwright/test";
export default defineConfig({testDir: "./e2e", testMatch: "clinical-demo.spec.ts", workers: 1, retries: 0, timeout: 45000, reporter: [["list"]], use: {baseURL: "http://localhost:3000", headless: true, trace: "off", screenshot: "only-on-failure"}});
