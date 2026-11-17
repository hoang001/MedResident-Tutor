import {test, expect} from "@playwright/test";
import fs from "node:fs";

const privatePath = process.env.CLINICAL_DEMO_ACCOUNTS;
test.skip(!privatePath, "Run explicitly against the prepared local development demo");
const credentials = privatePath ? JSON.parse(fs.readFileSync(privatePath, "utf8")) : {users: []};
const target = process.env.CLINICAL_DEMO_HOST ?? "http://host.docker.internal";

test.beforeEach(async ({page}) => {
  // Docker browser bridge only: forward real requests and actual server responses.
  // No fabricated API bodies, grades, images or authentication responses.
  await page.route(/^http:\/\/localhost:(3000|8000)\//, async route => {
    const real = await route.fetch({url: route.request().url().replace("http://localhost", target)});
    await route.fulfill({response: real});
  });
});

for (const key of ["CASE01", "XR01"]) {
  test(`authored ${key}: image, submit mock, source solution, reload and ownership`, async ({page}) => {
    const id = "CLINICAL_DEMO_V1_" + key;
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.goto("http://localhost:3000/login");
    await page.getByLabel("Email", {exact: true}).fill(credentials.users[0].email);
    await page.getByLabel("Mật khẩu", {exact: true}).fill(credentials.users[0].password);
    await page.getByRole("button", {name: "Đăng nhập", exact: true}).click();
    await expect(page).toHaveURL(/\/learn/);
    await page.goto(`http://localhost:3000/learn?question=${id}`);
    await expect(page.getByRole("combobox")).toHaveValue(id);
    await expect(page.getByTestId("clinical-image").first()).toBeVisible();
    await expect.poll(() => page.getByTestId("clinical-image").first().evaluate((i: HTMLImageElement) => i.complete && i.naturalWidth > 0)).toBeTruthy();
    await expect(page.getByTestId("clinical-solution")).toHaveCount(0);
    await expect(page.getByTestId("answer-annotation")).toHaveCount(0);
    const token = await page.evaluate(() => localStorage.getItem("access_token"));
    const fetched = await page.request.get(`${target}:8000/api/v1/practice/questions/${id}`, {headers: {Authorization: `Bearer ${token}`}});
    expect(fetched.status()).toBe(200);
    const question = await fetched.json();
    const encoded = JSON.stringify(question);
    for (const field of ["reference_answer", "criteria", "annotations", "source_refs", "storage_key", "source_image_id"]) expect(encoded).not.toContain(`"${field}"`);
    await page.screenshot({path: `/workspace/data/clinical-cases/exercises/audit/${key}-desktop.png`, fullPage: true});
    const popup = page.waitForEvent("popup");
    await page.getByRole("link", {name: /Mở ảnh 1 .*kích thước gốc/}).first().click();
    const zoom = await popup;
    expect(zoom.url()).toMatch(/^blob:/);
    await zoom.close();
    await page.getByLabel("Câu trả lời", {exact: true}).fill("Trả lời thử qua giao diện; chưa đánh giá năng lực.");
    await page.getByRole("button", {name: "Gửi câu trả lời", exact: true}).click();
    await expect(page.getByTestId("stage-status")).toContainText("Teaching: Đã lưu");
    await expect(page.getByTestId("clinical-solution")).toBeVisible();
    if (key === "XR01") await expect(page.getByTestId("answer-annotation")).toHaveCount(1);
    const attemptId = new URL(page.url()).searchParams.get("attempt");
    expect(attemptId).toBeTruthy();
    await page.reload();
    await expect(page.getByTestId("clinical-solution")).toBeVisible();
    expect(new URL(page.url()).searchParams.get("attempt")).toBe(attemptId);
    await page.setViewportSize({width: 390, height: 844});
    await expect(page.getByTestId("clinical-image").first()).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
    await page.screenshot({path: `/workspace/data/clinical-cases/exercises/audit/${key}-mobile.png`, fullPage: true});
    const login = await page.request.post(`${target}:8000/api/v1/auth/login`, {data: {email: credentials.users[1].email, password: credentials.users[1].password}});
    const otherToken = (await login.json()).access_token;
    const headers = {Authorization: `Bearer ${otherToken}`};
    expect((await page.request.get(`${target}:8000/api/v1/practice/attempts/${attemptId}`, {headers})).status()).toBe(404);
    expect((await page.request.post(`${target}:8000/api/v1/practice/attempts/${attemptId}/retry`, {headers})).status()).toBe(404);
    expect(errors).toEqual([]);
  });
}
