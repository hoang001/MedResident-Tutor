import {defineConfig} from "@playwright/test";
export default defineConfig({testDir: "./e2e", testMatch: "structured-demo.spec.ts", workers: 1, retries: 0, timeout: 45000, reporter: [["list"], ["junit", {outputFile: "/workspace/data/clinical-cases/exercises/structured/audit/browser-tests.xml"}]], use: {baseURL: "http://localhost:3000", headless: true, trace: "off", screenshot: "off"}});
