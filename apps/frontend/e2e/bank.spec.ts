import {test, expect, Page} from "@playwright/test";
import {randomUUID} from "node:crypto";
import {login, api, apiBase, submit, currentAttempt} from "./helpers";
async function admin(page: Page) {await login(page,"fixture-admin@example.com"); await page.getByRole("link",{name:"Ngân hàng câu hỏi",exact:true}).click(); await expect(page.getByRole("heading",{name:"Ngân hàng câu hỏi",exact:true})).toBeVisible(); await expect(page.getByRole("button",{name:"Tạo câu hỏi mới",exact:true})).toBeVisible();}
async function fillThree(page: Page, question: string) {
  await page.getByLabel("Nội dung câu hỏi",{exact:true}).fill(question);
  await page.getByLabel("Tên rubric",{exact:true}).fill("Synthetic UI rubric");
  await page.getByLabel("Điểm tối đa rubric",{exact:true}).fill("6");
  await page.getByRole("button",{name:"Thêm tiêu chí",exact:true}).click(); await page.getByRole("button",{name:"Thêm tiêu chí",exact:true}).click();
  for(let i=1;i<=3;i++) {
    await page.getByLabel(`Mô tả tiêu chí ${i}`,{exact:true}).fill(`Synthetic UI criterion ${i}`);
    await page.getByLabel(`Điểm tiêu chí ${i}`,{exact:true}).fill(String(i));
    const editor=page.getByTestId("criterion-editor").nth(i-1);
    await editor.getByRole("checkbox",{name:"Synthetic evidence A",exact:true}).check();
    if(i===3) await editor.getByRole("checkbox",{name:"Synthetic evidence B",exact:true}).check();
  }
}
test("admin bank lifecycle, learner practice, immutable snapshot, retirement and role guard",async({page,browser})=>{
  const question=`Synthetic bank question ${randomUUID()}`;
  await admin(page);
  await fillThree(page,question);
  await expect(page.getByTestId("criterion-total")).toHaveText("Tổng điểm tiêu chí: 6");
  const savedResponse=page.waitForResponse(r=>r.url().endsWith("/admin/questions")&&r.request().method()==="POST");
  await page.getByRole("button",{name:"Lưu câu hỏi và rubric",exact:true}).click();
  const q=await(await savedResponse).json();
  expect(q.question_id).toMatch(/^APP_Q_/);expect(q.criteria).toHaveLength(3);
  await expect(page.locator("main").getByRole("status")).toContainText("Đã lưu");
  await page.getByRole("button",{name:"Đưa vào sử dụng",exact:true}).click();
  await expect(page.getByRole("button",{name:"Ngừng sử dụng",exact:true})).toBeVisible();
  const learnerContext=await browser.newContext();const learner=await learnerContext.newPage();
  try {
    await login(learner);
    await expect(learner.getByRole("link",{name:"Ngân hàng câu hỏi",exact:true})).toHaveCount(0);
    await learner.getByRole("combobox").selectOption(q.question_id);
    await submit(learner,"Synthetic runtime answer from learner");
    await expect(learner.getByTestId("stage-status")).toContainText("Teaching: Đã lưu");
    const old=await currentAttempt(learner);
    expect(old.medical_evaluation.rubric_scores).toHaveLength(3);expect(old.medical_evaluation.max_score).toBe(6);expect(old.evidence).toHaveLength(2);
    await page.getByLabel("Mô tả tiêu chí 1",{exact:true}).fill("Changed current rubric criterion");
    await page.getByLabel("Điểm tiêu chí 1",{exact:true}).fill("4");
    await page.getByLabel("Điểm tối đa rubric",{exact:true}).fill("9");
    await page.getByRole("button",{name:"Lưu câu hỏi và rubric",exact:true}).click();
    await expect(page.locator("main").getByRole("status")).toContainText("Đã lưu");
    await learner.reload();await expect(learner.getByTestId("stage-status")).toContainText("Teaching: Đã lưu");
    expect(await currentAttempt(learner)).toEqual(old);
    await page.getByRole("button",{name:"Ngừng sử dụng",exact:true}).click();
    await expect(page.getByRole("button",{name:"Đưa vào sử dụng",exact:true})).toBeVisible();
    await learner.reload();await expect(learner.getByTestId("practice-result")).toBeVisible();
    await expect(learner.getByRole("combobox").locator(`option[value="${q.question_id}"]`)).toHaveCount(0);
    expect(await currentAttempt(learner)).toEqual(old);
    expect((await api(learner,"/admin/questions")).status()).toBe(403);
    const token=await learner.evaluate(()=>localStorage.getItem("access_token"));
    expect((await learner.request.post(apiBase+"/admin/questions",{headers:{Authorization:`Bearer ${token}`},data:{content:"forbidden"}})).status()).toBe(403);
    await learner.goto("/admin/questions");await expect(learner.getByRole("status")).toContainText("không có quyền");
    await expect(learner.getByLabel("Nội dung câu hỏi",{exact:true})).toHaveCount(0);
  } finally {await learnerContext.close();}
});

test("bank form rejects missing evidence/invalid total and source picker shows locators/review",async({page})=>{
  await admin(page);
  await page.getByLabel("Nội dung câu hỏi",{exact:true}).fill(`Validation fixture ${randomUUID()}`);
  await page.getByLabel("Mô tả tiêu chí 1",{exact:true}).fill("Synthetic criterion");
  await page.getByRole("button",{name:"Lưu câu hỏi và rubric",exact:true}).click();
  await expect(page.locator("main").getByRole("alert")).toContainText("ít nhất một evidence");
  await page.getByRole("checkbox",{name:"Synthetic evidence A",exact:true}).check();
  await page.getByLabel("Tìm SourceUnit",{exact:true}).fill("evidence B");
  await page.getByRole("button",{name:"Tìm evidence",exact:true}).click();
  await expect(page.getByRole("checkbox",{name:"Synthetic evidence A",exact:true})).toBeChecked();
  await page.getByLabel("Điểm tối đa rubric",{exact:true}).fill("99");
  await page.getByRole("button",{name:"Lưu câu hỏi và rubric",exact:true}).click();
  await expect(page.locator("main").getByRole("alert")).toContainText("tổng điểm");
  await page.getByRole("button",{name:"Xem evidence",exact:true}).first().click();
  await expect(page.locator("blockquote").last()).toContainText("Synthetic nonclinical");
  await expect(page.locator("aside")).toContainText("PDF 1–1");await expect(page.locator("aside")).toContainText("trang in 10");await expect(page.locator("aside")).toContainText("unverified");
});
