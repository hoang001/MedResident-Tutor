import {defineConfig} from "@playwright/test";
export default defineConfig({testDir:"./e2e",testMatch:"authoring.spec.ts",workers:1,retries:0,timeout:90000,reporter:[["list"]],use:{headless:true,screenshot:"only-on-failure"}});
