import {test, expect} from "@playwright/test";
import {login} from "./helpers";

test("keyboard skip link and password mismatch focus", async ({page}) => {
  await page.goto("/register");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", {name: "Chuyển đến nội dung chính"})).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();
  await page.getByLabel("Mật khẩu", {exact: true}).fill("Mismatch123!");
  await page.getByLabel("Xác nhận mật khẩu", {exact: true}).fill("Different123!");
  await page.getByRole("button", {name: "Tạo tài khoản", exact: true}).click();
  await expect(page.getByLabel("Xác nhận mật khẩu", {exact: true})).toBeFocused();
  await expect(page.getByText("Mật khẩu xác nhận không khớp.", {exact: true})).toBeVisible();
});

test("admin can cancel replacing unsaved edits or leaving", async ({page}) => {
  await login(page, "fixture-admin@example.com");
  await page.goto("/admin/questions");
  await page.getByLabel("Nội dung câu hỏi", {exact: true}).fill("Unsaved review fixture");
  page.once("dialog", dialog => dialog.dismiss());
  await page.getByRole("button", {name: "Tạo câu hỏi mới", exact: true}).click();
  await expect(page.getByLabel("Nội dung câu hỏi", {exact: true})).toHaveValue("Unsaved review fixture");
  page.once("dialog", dialog => dialog.dismiss());
  await page.getByRole("link", {name: "Tổng quan", exact: true}).click();
  await expect(page).toHaveURL(/\/admin\/questions/);
  page.once("dialog", dialog => dialog.accept());
  await page.getByRole("button", {name: "Tạo câu hỏi mới", exact: true}).click();
  await expect(page.getByLabel("Nội dung câu hỏi", {exact: true})).toHaveValue("");
});

test("workspace renders without overflow at mobile tablet desktop sizes", async ({page}) => {
  for (const width of [390, 768, 1440]) {
    await page.setViewportSize({width, height: 900});
    await login(page, "fixture-admin@example.com");
    for (const route of ["dashboard", "curriculum", "knowledge", "exams", "progress", "learn", "sources", "admin/questions", "admin/documents", "login", "register"]) {
      if (route === "login") await page.evaluate(() => localStorage.removeItem("access_token"));
      await page.goto(`/${route}`);
      await page.waitForLoadState("networkidle");
      await expect(page.locator("main h1")).toBeVisible();
      await expect(page.getByRole("navigation", {name: "Điều hướng chính"}).locator('[aria-current="page"]')).toHaveCount(1);
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({path: `../../docs/frontend-review/screenshots/${route.replaceAll("/", "-")}-${width}.png`, fullPage: true});
    }
  }
});
test("registration creates a usable account and logout clears authentication", async ({page}) => {
  await page.goto("/register");
  await page.getByLabel("Họ tên", {exact: true}).fill("Frontend review fixture");
  await page.getByLabel("Email", {exact: true}).fill(`review-${crypto.randomUUID()}@example.com`);
  await page.getByLabel("Mật khẩu", {exact: true}).fill("BrowserFixtureOnly123!");
  await page.getByLabel("Xác nhận mật khẩu", {exact: true}).fill("BrowserFixtureOnly123!");
  await page.getByRole("button", {name: "Tạo tài khoản", exact: true}).click();
  await expect(page).toHaveURL(/\/learn/);
  await expect(page.getByLabel("Câu trả lời", {exact: true})).toBeEnabled();
  await page.getByRole("button", {name: "Đăng xuất", exact: true}).click();
  await expect(page).toHaveURL(/reason=logout/);
  expect(await page.evaluate(() => localStorage.getItem("access_token"))).toBeNull();
});

test("admin upload announces success and preserves file processing status", async ({page}) => {
  await login(page, "fixture-admin@example.com");
  await page.goto("/admin/documents");
  await page.getByLabel("Tên hiển thị (không bắt buộc)").fill("Synthetic frontend review document");
  await page.getByLabel("Tệp tài liệu", {exact: true}).setInputFiles({name: "review.txt", mimeType: "text/plain", buffer: Buffer.from("Synthetic interface test; no medical content.")});
  await page.getByRole("button", {name: "Tải tài liệu lên", exact: true}).click();
  await expect(page.getByRole("status")).toContainText("đã tải lên");
  await expect(page.getByRole("status")).toContainText("Chưa chạy OCR hoặc lập chỉ mục");
});