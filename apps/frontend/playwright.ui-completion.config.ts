import {defineConfig} from "@playwright/test";
export default defineConfig({testDir:"./e2e",testMatch:"ui-completion.spec.ts",workers:1,retries:0,timeout:180000,reporter:[["list"]],outputDir:"../../data/authoring/ui-completion-20261116/playwright",use:{locale:"vi-VN",timezoneId:"Asia/Ho_Chi_Minh",headless:true,screenshot:"only-on-failure",actionTimeout:12000,navigationTimeout:25000}});
