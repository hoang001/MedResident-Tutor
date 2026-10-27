import {test, expect} from "@playwright/test";
import {randomUUID, createHmac} from "node:crypto";
import {apiBase, api, currentAttempt, login, signIn, submit} from "./helpers";

test("invalid email displays field error with HTTP422, no500", async ({page}) => {
  await page.goto("/login");
  await page.getByLabel("Email", {exact: true}).fill("not-an-email");
  await page.getByLabel("Mật khẩu", {exact: true}).fill("dummy-test-only");
  const response = page.waitForResponse(r => r.url().endsWith("/auth/login"));
  await page.getByRole("button", {name: "Đăng nhập", exact: true}).click();
  expect((await response).status()).toBe(422);
  await expect(page.locator("#email-error")).toHaveText("Địa chỉ email không hợp lệ.");
  await expect(page.locator("main").getByRole("alert")).toContainText("kiểm tra");
});

test("login, submit, Medical/Teaching results, evidence, reload/history and new attempt", async ({page}) => {
  await login(page);
  await expect(page.getByRole("combobox")).toHaveValue("ORTHO_B21CN1_Q_0001");
  const answer = `Success fixture ${randomUUID()}`;
  await submit(page, answer);
  await expect(page.getByTestId("stage-status")).toContainText("Teaching: Đã lưu");
  await expect(page.getByRole("heading", {name: "Ý đúng", exact: true})).toBeVisible();
  await expect(page.getByRole("heading", {name: "Ý sai", exact: true})).toBeVisible();
  await expect(page.getByRole("heading", {name: "Ý thiếu", exact: true})).toBeVisible();
  await expect(page.getByText("Trang PDF 16–16; trang in 15.")).toBeVisible();
  await expect(page.getByText(/Trạng thái chuyên gia duyệt: chưa xác minh/)).toBeVisible();
  const original = await currentAttempt(page);
  expect(original.medical_evaluation.rubric_scores).toHaveLength(2);
  expect(original.medical_evaluation.max_score).toBe(2);
  await page.reload();
  await expect(page.getByTestId("practice-result")).toContainText(answer);
  expect((await currentAttempt(page)).id).toBe(original.id);
  await page.getByRole("button", {name: "ORTHO_B21CN1_Q_0001 · completed", exact: true}).first().click();
  expect((await currentAttempt(page)).id).toBe(original.id);
  await page.getByRole("button", {name: "Tạo lượt mới", exact: true}).click();
  await expect(page.getByLabel("Câu trả lời", {exact: true})).toHaveValue("");
  await submit(page, answer);
  await expect(page.getByTestId("stage-status")).toContainText("Teaching: Đã lưu");
  expect((await currentAttempt(page)).id).not.toBe(original.id);
});

test("server commits but browser loses real response: reload reuses key with no duplicate", async ({page}) => {
  await login(page);
  const answer = `Lost-response fixture ${randomUUID()}`;
  let firstKey = "";
  // Forward the real request to the real backend, consume its real response,
  // then simulate transport loss. Never fulfill with a fabricated API response.
  await page.route("**/api/v1/practice/attempts", async route => {
    if (route.request().method() !== "POST") {await route.continue(); return;}
    firstKey = route.request().headers()["idempotency-key"];
    const realResponse = await route.fetch();
    expect(realResponse.status()).toBe(200);
    await realResponse.body();
    await route.abort("failed");
  });
  await submit(page, answer);
  await expect(page.locator("main").getByRole("alert")).toContainText("Mất kết nối");
  const before = (await (await api(page, "/practice/attempts")).json()).filter((a: {student_answer: string}) => a.student_answer === answer);
  expect(before).toHaveLength(1);
  await page.unroute("**/api/v1/practice/attempts");
  await page.reload();
  await expect(page.getByRole("button", {name: "Gửi lại lần nộp đang chờ"})).toBeVisible();
  const repeated = page.waitForRequest(r => r.url().endsWith("/practice/attempts") && r.method() === "POST");
  await page.getByRole("button", {name: "Gửi lại lần nộp đang chờ"}).click();
  expect((await repeated).headers()["idempotency-key"]).toBe(firstKey);
  await expect(page.getByTestId("stage-status")).toContainText("Teaching: Đã lưu");
  expect((await currentAttempt(page)).id).toBe(before[0].id);
  expect((await (await api(page, "/practice/attempts")).json()).filter((a: {student_answer: string}) => a.student_answer === answer)).toHaveLength(1);
});

test("expired session redirects once, returns safely and restores only same-user draft", async ({page}) => {
  await login(page);
  const draft = `Private draft ${randomUUID()}`;
  await page.getByLabel("Câu trả lời", {exact: true}).fill(draft);
  const token = await page.evaluate(() => localStorage.getItem("access_token"));
  const claims = JSON.parse(Buffer.from(token!.split(".")[1], "base64url").toString());
  const header = Buffer.from(JSON.stringify({alg: "HS256", typ: "JWT"})).toString("base64url");
  const payload = Buffer.from(JSON.stringify({...claims, exp: Math.floor(Date.now()/1000)+2})).toString("base64url");
  const signature = createHmac("sha256", "isolated-browser-tests-only-secret-at-least-32-characters").update(`${header}.${payload}`).digest("base64url");
  // Genuine signed short-lived JWT; exercise idle expiry without a reload.
  const shortToken = `${header}.${payload}.${signature}`;
  await page.evaluate(value => {localStorage.setItem("access_token", value); window.dispatchEvent(new Event("auth-changed"));}, shortToken);
  await expect(page).toHaveURL(/\/login\?reason=expired&next=/);
  await expect(page.getByRole("status")).toContainText("hết hạn");
  expect((await page.request.get(apiBase + "/auth/me", {headers: {Authorization: `Bearer ${shortToken}`}})).status()).toBe(401);
  await signIn(page);
  await expect(page.getByLabel("Câu trả lời", {exact: true})).toHaveValue(draft);
  await page.getByRole("button", {name: "Đăng xuất", exact: true}).click();
  await expect(page).toHaveURL(/reason=logout/);
  expect(await page.evaluate(() => localStorage.getItem("access_token"))).toBeNull();
  await signIn(page, "second@example.com");
  await expect(page.getByLabel("Câu trả lời", {exact: true})).toHaveValue("");
  await expect(page.locator("main")).not.toContainText(draft);
});

test("different user cannot read or retry previous user's attempt", async ({page}) => {
  await login(page);
  const answer = `Owner fixture ${randomUUID()}`;
  await submit(page, answer);
  await expect(page.getByTestId("stage-status")).toContainText("Teaching: Đã lưu");
  const original = await currentAttempt(page);
  await page.getByRole("button", {name: "Đăng xuất", exact: true}).click();
  await expect(page).toHaveURL(/reason=logout/);
  await signIn(page, "second@example.com");
  await page.goto(`/learn?attempt=${original.id}`);
  await expect(page.locator("main").getByRole("alert")).toContainText("Không tìm thấy");
  await expect(page.getByTestId("practice-result")).toHaveCount(0);
  await expect(page.locator("main")).not.toContainText(answer);
  expect((await api(page, `/practice/attempts/${original.id}`)).status()).toBe(404);
  const token = await page.evaluate(() => localStorage.getItem("access_token"));
  expect((await page.request.post(`${apiBase}/practice/attempts/${original.id}/retry`, {headers: {Authorization: `Bearer ${token}`}})).status()).toBe(404);
});

test("login rejects external return path without redirect loop", async ({page}) => {
  await page.goto("/login?next=https://outside.invalid/steal");
  await signIn(page);
  expect(new URL(page.url()).pathname).toBe("/learn");
});


test("server401 redirects to login once and keeps the current draft", async ({page}) => {
  await login(page);
  const draft = `401 draft ${randomUUID()}`;
  await page.getByLabel("Câu trả lời", {exact: true}).fill(draft);
  await page.evaluate(() => {
    const token = localStorage.getItem("access_token")!;
    const parts = token.split(".");
    localStorage.setItem("access_token", `${parts[0]}.${parts[1]}.invalid-signature`);
  });
  const denied = page.waitForResponse(r => r.url().endsWith("/auth/me") && r.status() === 401);
  await page.reload();
  await denied;
  await expect(page).toHaveURL(/\/login\?reason=expired&next=/);
  await signIn(page);
  await expect(page.getByLabel("Câu trả lời", {exact: true})).toHaveValue(draft);
});
