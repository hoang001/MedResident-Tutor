import {test, expect} from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const privatePath = process.env.CLINICAL_DEMO_ACCOUNTS;
test.skip(!privatePath, "Use only the prepared local development demo accounts");
const credentials = privatePath ? JSON.parse(fs.readFileSync(privatePath, "utf8")) : {users: []};
const target = process.env.CLINICAL_DEMO_HOST ?? "http://host.docker.internal";
const bundle = "/workspace/data/clinical-cases/exercises";
const ownershipFile = path.join(bundle, "structured/audit/browser-owned-attempts.json");
type Owned = {user_id: string; key: string; question_id: string};
const owned: Owned[] = [];

test.beforeEach(async ({page}) => {
  // Transport bridge only. Every response comes from the running FE/BE/PostgreSQL.
  await page.route(/^http:\/\/localhost:(3000|8000)\//, async route => {
    const real = await route.fetch({url: route.request().url().replace("http://localhost", target)});
    await route.fulfill({response: real});
  });
});

for (const short of ["CASE01", "XR01"]) {
  test(`structured ${short}: real form, source feedback, images, reload, ownership`, async ({page}) => {
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    const qid = "CLINICAL_DEMO_V2_" + short;
    const spec = JSON.parse(fs.readFileSync(path.join(bundle, "structured", qid + ".json"), "utf8"));
    await page.goto("/login");
    await page.getByLabel("Email", {exact: true}).fill(credentials.users[0].email);
    await page.getByLabel("Mật khẩu", {exact: true}).fill(credentials.users[0].password);
    await page.getByRole("button", {name: "Đăng nhập", exact: true}).click();
    await expect(page).toHaveURL(/\/learn/);
    const token = await page.evaluate(() => localStorage.getItem("access_token"));
    const headers = {Authorization: `Bearer ${token}`};
    const me = await (await page.request.get(`${target}:8000/api/v1/auth/me`, {headers})).json();
    page.on("request", request => {
      if (request.method() === "POST" && request.url().endsWith("/practice/attempts")) {
        const body = request.postDataJSON();
        owned.push({user_id: me.id, question_id: body.question_id, key: request.headers()["idempotency-key"]});
        fs.writeFileSync(ownershipFile, JSON.stringify(owned, null, 2));
      }
    });
    await page.goto(`/learn?question=${qid}`);
    await expect(page.getByRole("combobox")).toHaveValue(qid);
    await expect(page.getByTestId("clinical-image").first()).toBeVisible();
    await expect.poll(() => page.getByTestId("clinical-image").first().evaluate((i: HTMLImageElement) => i.complete && i.naturalWidth > 0)).toBeTruthy();
    await expect(page.getByTestId("clinical-solution")).toHaveCount(0);
    await expect(page.getByTestId("answer-annotation")).toHaveCount(0);
    const pre = await page.request.get(`${target}:8000/api/v1/practice/questions/${qid}`, {headers});
    expect(pre.status()).toBe(200);
    for (const field of ["correct_option_id", "criterion_id", "incorrect_feedback", "evidence_ids", "reference_answer", "annotations", "source_refs", "source_image_id", "storage_key"]) expect(await pre.text()).not.toContain(`"${field}"`);
    const neutralImage = (await pre.json()).clinical_exercise.images[0];
    expect((await page.request.get(`${target}:8000/api/v1${neutralImage.url}`)).status()).toBe(401);
    if (short === "XR01") {
      await page.getByRole("button", {name: "Xem ảnh 1 của bài tập lớn với lưới"}).click();
      const dialog = page.getByRole("dialog");
      await expect(dialog).toBeVisible();
      await expect(dialog.locator("svg text")).toHaveText(["1,1","1,2","1,3","2,1","2,2","2,3","3,1","3,2","3,3"]);
      await expect(dialog.getByTestId("answer-annotation")).toHaveCount(0);
      await page.getByRole("button", {name: "Đóng ảnh lớn"}).click();
      await expect(dialog).not.toBeVisible();
    }
    await page.screenshot({path: path.join(bundle, `structured/audit/${short}-before-desktop.png`), fullPage: true});
    for (const part of spec.parts.filter((p: {max_score: number}) => p.max_score)) {
      const option = part.options.find((o: {id: string}) => o.id === part.correct_option_id);
      await page.getByRole("radio", {name: option.label, exact: true}).check();
    }
    const explanation = "  Giải thích tự do để lưu lại; không tính vào điểm.  ";
    await page.getByLabel("Giải thích ngắn", {exact: false}).fill(explanation);
    // Draft survives a real page reload without an extra attempt.
    await page.reload();
    await expect(page.getByLabel("Giải thích ngắn", {exact: false})).toHaveValue(explanation);
    await page.getByRole("button", {name: "Gửi câu trả lời", exact: true}).click();
    await expect(page.getByTestId("structured-score")).toHaveText("Điểm: 2/2");
    await expect(page.getByTestId("stage-status")).toHaveCount(0);
    await expect(page.getByTestId("clinical-solution")).toBeVisible();
    await expect(page.getByTestId("result-explanation")).toContainText(explanation.trim());
    await expect(page.getByRole("button", {name: "Đã nộp bài"})).toBeDisabled();
    if (short === "XR01") await expect(page.getByTestId("answer-annotation")).toHaveCount(1);
    const id = new URL(page.url()).searchParams.get("attempt");
    expect(id).toBeTruthy();
    const result = await (await page.request.get(`${target}:8000/api/v1/practice/attempts/${id}`, {headers})).json();
    expect(result.execution_mode).toBe("structured");
    expect(result.medical_evaluation).toBeNull();
    expect(result.teaching_feedback).toBeNull();
    expect(result.provider_metadata.model_calls).toBe(0);
    const replay = await page.request.post(`${target}:8000/api/v1/practice/attempts`, {headers: {...headers, "Idempotency-Key": owned.at(-1)!.key}, data: {question_id: qid, revision_id: qid, structured_answers: Object.fromEntries(result.structured_result.parts.map((p: {id: string; answer: string | null}) => [p.id, p.answer]))}});
    expect(replay.status()).toBe(200);
    expect((await replay.json()).id).toBe(id);
    await page.reload();
    await expect(page.getByTestId("structured-score")).toHaveText("Điểm: 2/2");
    await page.screenshot({path: path.join(bundle, `structured/audit/${short}-result-desktop.png`), fullPage: true});
    await page.setViewportSize({width: 390, height: 844});
    await expect(page.getByTestId("clinical-solution")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
    await page.screenshot({path: path.join(bundle, `structured/audit/${short}-result-mobile.png`), fullPage: true});
    const login = await page.request.post(`${target}:8000/api/v1/auth/login`, {data: {email: credentials.users[1].email, password: credentials.users[1].password}});
    const other = {Authorization: `Bearer ${(await login.json()).access_token}`};
    const attemptUrl = `${target}:8000/api/v1/practice/attempts/${id}`;
    expect((await page.request.get(attemptUrl, {headers: other})).status()).toBe(404);
    expect((await page.request.post(attemptUrl + "/retry", {headers: other})).status()).toBe(404);
    expect((await page.request.get(`${target}:8000/api/v1${result.clinical_exercise.images[0].url}`, {headers: other})).status()).toBe(404);
    expect(errors).toEqual([]);
  });
}

test("internal review contains ten structured definitions and eight staging entries", async ({page}) => {
  await page.goto("file:///workspace/data/clinical-cases/exercises/review.html");
  await expect(page.locator("article")).toHaveCount(10);
  await expect(page.getByText("Staging, không import", {exact: false})).toHaveCount(8);
  await expect(page.getByText("Bản structured: đề → lựa chọn → đáp án → điểm → nhận xét → nguồn", {exact: true})).toHaveCount(10);
  const demo = page.locator("article#CLINICAL_DEMO_V1_XR01");
  await demo.locator("details").nth(1).locator("summary").click();
  await expect(demo.getByRole("heading", {name: "Bản structured: đề → lựa chọn → đáp án → điểm → nhận xét → nguồn"})).toBeVisible();
});
