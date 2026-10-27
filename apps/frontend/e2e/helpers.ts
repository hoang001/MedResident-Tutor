import {Page, expect} from "@playwright/test";
export const apiBase = process.env.E2E_API_URL ?? "http://localhost:8100/api/v1";
export async function signIn(page: Page, email = "first@example.com") {
  await page.getByLabel("Email", {exact: true}).fill(email);
  await page.getByLabel("Mật khẩu", {exact: true}).fill("BrowserFixtureOnly123!");
  await page.getByRole("button", {name: "Đăng nhập", exact: true}).click();
  await expect(page).toHaveURL(/\/learn/);
  await expect(page.getByLabel("Câu trả lời", {exact: true})).toBeEnabled();
}
export async function login(page: Page, email?: string) {await page.goto("/login"); await signIn(page, email);}
export async function api(page: Page, path: string) {
  const token = await page.evaluate(() => localStorage.getItem("access_token"));
  return page.request.get(apiBase + path, {headers: {Authorization: `Bearer ${token}`}});
}
export async function currentAttempt(page: Page) {
  const id = new URL(page.url()).searchParams.get("attempt");
  expect(id).toBeTruthy();
  const response = await api(page, `/practice/attempts/${id}`);
  expect(response.status()).toBe(200);
  return response.json();
}
export async function submit(page: Page, text: string) {
  await page.getByLabel("Câu trả lời", {exact: true}).fill(text);
  await page.getByRole("button", {name: "Gửi câu trả lời", exact: true}).click();
}
