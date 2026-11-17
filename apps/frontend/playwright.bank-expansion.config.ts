import {defineConfig} from "@playwright/test";
export default defineConfig({testDir:"./e2e",testMatch:"bank-expansion.spec.ts",workers:1,retries:0,timeout:120000,reporter:[["list"]],outputDir:"../../data/authoring/bank-expansion-20261116/playwright",use:{headless:true,screenshot:"only-on-failure"}});
