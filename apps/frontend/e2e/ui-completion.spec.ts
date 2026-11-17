import {test,expect,Page} from "@playwright/test";
import fs from "node:fs";
const root="/workspace/data/authoring/ui-completion-20261116";
const base="http://host.docker.internal:3000";
const before=process.env.UI_PHASE==="before";
async function connect(page:Page){
  await page.route("http://localhost:8000/api/v1/**",route=>route.continue({url:route.request().url().replace("http://localhost:8000","http://host.docker.internal:8106")}));
}
async function api(page:Page,path:string,method="GET",body?:unknown){
  return page.evaluate(async({path,method,body})=>{
    const r=await fetch("http://localhost:8000/api/v1"+path,{method,headers:{Authorization:"Bearer "+localStorage.getItem("access_token"),"Content-Type":"application/json"},...(body?{body:JSON.stringify(body)}:{})});
    return {status:r.status,data:await r.json()};
  },{path,method,body});
}
async function shot(page:Page,name:string){
  await expect(page.locator("main")).toBeVisible();
  await expect(page.locator('main [role="status"]').filter({hasText:/^Đang (tải|mở|đọc|xác thực|tìm|kiểm tra)/})).toHaveCount(0,{timeout:20000});
  await page.evaluate(()=>document.fonts.ready);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),name).toBe(true);
  await page.screenshot({path:`${root}/after-${name}.png`,fullPage:true,animations:"disabled"});
}
async function login(page:Page,admin=false){
  await page.goto(base+"/login");
  await page.getByLabel("Email",{exact:true}).fill(admin?"ui-admin@example.com":"ui-student@example.com");
  await page.getByLabel("Mật khẩu",{exact:true}).fill("UiFixtureOnly123!");
  await page.getByRole("button",{name:"Đăng nhập",exact:true}).click();
  await expect(page).not.toHaveURL(/\/login/);
}
async function capture(page:Page,role:string,paths:Record<string,string>){
  for(const [label,path] of Object.entries(paths)){
    for(const width of [1440,390]){
      await page.setViewportSize({width,height:1000}); await page.goto(base+path);
      await expect(page.locator("main")).toBeVisible();
      await expect(page.locator('main [role="status"]').filter({hasText:/^Đang (tải|mở|đọc|xác thực|tìm|kiểm tra)/})).toHaveCount(0,{timeout:20000});
      await page.evaluate(()=>document.fonts.ready);
      const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
      if(!before)expect(overflow,label+" "+width).toBe(false);
      await page.screenshot({path:`${root}/${before?"before":"after"}-${role}-${label}-${width}.png`,fullPage:true,animations:"disabled"});
    }
  }
}
test("UI audit and complete learner/admin workflow",async({page,browser})=>{
  await connect(page); await login(page);
  await capture(page,"student",{overview:"/dashboard",practice:"/learn?question=QB26_SHOULDER_STABILIZERS",library:"/knowledge",progress:"/progress"});
  const adminContext=await browser.newContext({locale:"vi-VN",timezoneId:"Asia/Ho_Chi_Minh"}); const admin=await adminContext.newPage();
  await connect(admin); await login(admin,true);
  await capture(admin,"admin",{bank:"/admin/questions",documents:"/admin/documents"});
  if(before){await adminContext.close();return;}
  expect(await admin.evaluate(()=>document.fonts.check('700 28px "Source Sans 3"',"Chấn thương chỉnh hình"))).toBe(true);
  fs.writeFileSync(root+"/capture-after-initial.json",JSON.stringify({captured:true,viewport_widths:[1440,390],main_database_writes:0}));
  await capture(page,"student",{catalog:"/learn",sources:"/sources",curriculum:"/curriculum",selfstudy:"/exams",account:"/account"});
  const errors:string[]=[];
  for(const p of [page,admin])p.on("pageerror",e=>errors.push(e.message));
  let modelRequests=0;
  await admin.route("**/api/v1/admin/authoring/{retrieve,propose}",route=>{modelRequests++;return route.abort();});
  const title="Bài kiểm thử giao diện · nguồn tổng hợp";
  await admin.setViewportSize({width:1440,height:1000});
  await admin.goto(base+"/admin/questions");
  await admin.getByRole("button",{name:"Tạo câu hỏi mới",exact:true}).click();
  await admin.getByRole("button",{name:"Lưu bản nháp",exact:true}).click();
  await expect(admin.locator("#bank-content-error")).toHaveText("Nhập nội dung câu hỏi.");
  await admin.getByLabel("Học phần",{exact:true}).fill("Học phần kiểm thử");
  await admin.getByLabel("Chủ đề",{exact:true}).fill("Chủ đề kiểm thử");
  await admin.getByLabel("Nội dung câu hỏi",{exact:true}).fill(title);
  await admin.getByLabel("Đáp án tham khảo",{exact:true}).fill("Đáp án tổng hợp chỉ dùng để kiểm thử UI.");
  await admin.getByLabel("Nội dung cần đạt",{exact:true}).fill("Nêu được ý chính từ nguồn tổng hợp.");
  await admin.getByLabel("Tìm đoạn nguồn",{exact:true}).fill("FIXTURE_SU_A");
  await admin.getByRole("button",{name:"Tìm nguồn",exact:true}).click();
  await expect(admin.locator("#question-sources .source-choice input[type=checkbox]")).toHaveCount(1);
  await admin.locator("#question-sources .source-choice input[type=checkbox]").check();
  await admin.getByRole("button",{name:"Đọc toàn bộ đoạn trích",exact:true}).click();
  await expect(admin.getByRole("region",{name:"Toàn bộ đoạn nguồn"})).toBeFocused();
  await admin.getByText("Tìm nguồn và đề xuất tự động",{exact:true}).click();
  await expect(admin.getByText(/Đề xuất tự động chưa được bật/)).toBeVisible();
  await admin.getByText("Tìm nguồn và đề xuất tự động",{exact:true}).click();
  await admin.getByRole("button",{name:"Lưu bản nháp",exact:true}).click();
  await expect(admin.getByText(/Đã lưu bản nháp\. Lưu và phát hành/)).toBeVisible();
  await admin.setViewportSize({width:390,height:1000});
  await admin.getByRole("tab",{name:"Đề & tiêu chí",exact:true}).click();
  await admin.setViewportSize({width:1440,height:1000});
  await shot(admin,"admin-editor-1440");
  await admin.setViewportSize({width:390,height:1000});
  await shot(admin,"admin-editor-390");
  await admin.getByRole("tab",{name:"Tài liệu nguồn",exact:true}).click();
  await expect(admin.getByLabel("Tìm đoạn nguồn",{exact:true})).toBeVisible();
  await shot(admin,"admin-sources-390");
  await admin.getByRole("tab",{name:"Đề & tiêu chí",exact:true}).click();
  await admin.getByRole("button",{name:"Về danh sách",exact:true}).click();
  await admin.setViewportSize({width:1440,height:1000});
  await admin.locator(".filters input[type=search]").fill(title);
  await admin.getByRole("button",{name:"Tìm câu hỏi",exact:true}).click();
  await expect(admin.getByRole("button",{name:"Mở biên soạn",exact:true})).toHaveCount(1);
  await admin.getByRole("button",{name:"Mở biên soạn",exact:true}).click();
  await expect(admin.getByLabel("Nội dung câu hỏi",{exact:true})).toHaveValue(title);
  await admin.getByLabel("Đáp án tham khảo",{exact:true}).fill("Đáp án tổng hợp đã sửa, chỉ dùng kiểm thử UI.");
  await admin.getByRole("button",{name:"Lưu bản nháp",exact:true}).click();
  await expect(admin.getByRole("button",{name:"Phát hành câu hỏi",exact:true})).toBeDisabled();
  await admin.getByRole("checkbox",{name:/Đã kiểm tra đề, đáp án/}).check();
  await admin.getByRole("button",{name:"Phát hành câu hỏi",exact:true}).click();
  await expect(admin.getByText(/Đã phát hành trong ứng dụng\./)).toBeVisible();
  const match=(await api(admin,"/admin/question-catalog?q="+encodeURIComponent(title))).data.items[0];
  expect(match.is_available).toBe(true);

  await page.setViewportSize({width:1440,height:1000});
  await page.goto(base+"/learn");
  await expect(page.getByRole("button",{name:"Trang sau",exact:true})).toBeEnabled();
  await page.getByRole("button",{name:"Trang sau",exact:true}).click();
  await expect(page.getByRole("navigation",{name:"Phân trang",exact:true})).toContainText("11–20");
  await page.getByLabel("Tìm bài tập",{exact:true}).fill("zz-no-matches-ui");
  await page.getByRole("button",{name:"Tìm bài tập",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Chưa có bài phù hợp"})).toBeVisible();
  await page.getByLabel("Tìm bài tập",{exact:true}).fill(title);
  await page.getByRole("button",{name:"Tìm bài tập",exact:true}).click();
  await page.getByRole("link",{name:"Mở bài",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Đề bài",exact:true})).toBeVisible();
  await expect(page.getByText(/Đáp án tổng hợp đã sửa/)).toHaveCount(0);
  await expect(page.getByRole("heading",{name:/Tài liệu đối chiếu/})).toHaveCount(0);
  const answer="Câu trả lời kiểm thử, phải được giữ lại nếu mạng lỗi.";
  await page.getByLabel("Câu trả lời",{exact:true}).fill(answer);
  await page.route("**/api/v1/practice/attempts",async route=>{
    if(route.request().method()==="POST"){await page.unroute("**/api/v1/practice/attempts");await route.abort("failed");}else await route.fallback();
  });
  await page.getByRole("button",{name:"Gửi câu trả lời",exact:true}).click();
  await expect(page.locator("main").getByRole("alert")).toBeVisible();
  await expect(page.getByLabel("Câu trả lời",{exact:true})).toHaveValue(answer);
  await page.getByRole("button",{name:"Gửi câu trả lời",exact:true}).click();
  await expect(page.getByRole("button",{name:"Thử lại phản hồi",exact:true})).toBeVisible();
  await expect(page.getByRole("heading",{name:"Đánh giá nội dung",exact:true})).toBeVisible();
  await expect(page.getByTestId("practice-result")).toContainText(/mô phỏng/i);
  const attemptId=new URL(page.url()).searchParams.get("attempt")!;
  const partial=(await api(page,"/practice/attempts/"+attemptId)).data;
  expect(partial.status).toBe("teaching_failed");
  await shot(page,"student-partial-result-1440");
  await page.setViewportSize({width:390,height:1000});
  await shot(page,"student-partial-result-390");
  await page.getByRole("button",{name:"Thử lại phản hồi",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Phản hồi hướng dẫn",exact:true})).toBeVisible();
  const completed=(await api(page,"/practice/attempts/"+attemptId)).data;
  expect(completed.status).toBe("completed");
  expect(completed.medical_evaluation).toEqual(partial.medical_evaluation);
  expect(completed.evidence).toEqual(partial.evidence);
  expect(completed.snapshot_hash).toEqual(partial.snapshot_hash);
  const savedAnswer=page.locator("details.source-details").first();
  await savedAnswer.locator("summary").focus();await page.keyboard.press("Enter");
  await expect(savedAnswer).toHaveAttribute("open","");await expect(savedAnswer).toContainText(answer);
  await page.locator("details.source-details").last().locator("summary").click();
  await expect(page.locator("blockquote").last()).toBeVisible();
  await shot(page,"student-result-390");
  await page.setViewportSize({width:1440,height:1000});
  await shot(page,"student-result-1440");
  const historyCount=(await api(page,"/practice/history")).data.overall_total;
  await page.getByRole("link",{name:"Mở trong lịch sử",exact:true}).click();
  await page.reload();
  await expect(page.getByRole("heading",{name:"Phản hồi hướng dẫn",exact:true})).toBeVisible();
  expect((await api(page,"/practice/attempts/"+attemptId)).data).toEqual(completed);
  expect((await api(page,"/practice/history")).data.overall_total).toBe(historyCount);
  await page.goto(base+"/history");await shot(page,"student-history-1440");
  await page.setViewportSize({width:390,height:1000});await shot(page,"student-history-390");
  await page.getByRole("button",{name:"Mở điều hướng",exact:true}).click();
  await expect(page.getByRole("dialog")).toBeVisible();await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page.setViewportSize({width:768,height:1000});await shot(page,"student-history-768");

  const clinical=(await api(page,"/practice/catalog?limit=100")).data.items.find((q:{structured_exercise?:unknown})=>q.structured_exercise);
  expect(clinical).toBeTruthy();
  await page.goto(base+"/learn?question="+encodeURIComponent(clinical.question_id));
  await expect(page.getByTestId("clinical-image").first()).toBeVisible();
  await expect(page.getByTestId("answer-annotation")).toHaveCount(0);
  await page.getByRole("button",{name:/Xem ảnh lớn/}).first().click();
  await expect(page.getByRole("dialog")).toBeVisible();await page.keyboard.press("Escape");
  await page.locator("input[type=radio]").first().check();
  await page.getByRole("button",{name:"Gửi câu trả lời",exact:true}).click();
  await expect(page.getByTestId("structured-score")).toBeVisible();
  await expect(page.getByText(/Evidence for CLINICAL_DEMO/)).toHaveCount(0);
  await shot(page,"student-structured-result-768");
  await page.setViewportSize({width:390,height:1000});await shot(page,"student-structured-result-390");
  expect((await api(page,"/admin/question-catalog")).status).toBe(403);
  await page.goto(base+"/admin/questions");
  await expect(page.getByText("Bạn không có quyền quản trị.",{exact:true})).toBeVisible();
  await page.goto(base+"/account");
  await page.getByRole("button",{name:"Đăng xuất",exact:true}).last().click();
  await expect(page).toHaveURL(/\/login/);
  await page.goto(base+"/history");await expect(page).toHaveURL(/\/login/);
  expect(modelRequests).toBe(0);expect(errors).toEqual([]);
  fs.writeFileSync(root+"/browser-assertions.json",JSON.stringify({admin_draft_edit_publish:true,student_search_pagination_empty:true,network_error_keeps_answer:true,teaching_failure_keeps_medical:true,manual_retry_only:true,history_snapshot_unchanged:true,structured_images_zoom_annotation_guard:true,logout_and_role_boundaries:true,viewport_widths:[1440,768,390],model_requests:modelRequests,main_database_writes:0,page_errors:errors},null,2));
  await adminContext.close();
});

test("a lost response after commit survives reload without duplicate grading",async({page})=>{
  test.skip(before,"Baseline capture only");
  await connect(page);await login(page);
  await page.goto(base+"/learn?question=QB26_SHOULDER_STABILIZERS");
  const answer="Bài kiểm thử mất phản hồi sau khi server đã lưu.";
  await page.getByLabel("Câu trả lời",{exact:true}).fill(answer);
  let key="";
  await page.route("**/api/v1/practice/attempts",async route=>{
    if(route.request().method()!=="POST")return route.fallback();
    key=route.request().headers()["idempotency-key"];
    const response=await route.fetch({url:route.request().url().replace("http://localhost:8000","http://host.docker.internal:8106")});
    expect(response.status()).toBe(200);await response.body();await route.abort("failed");
  });
  await page.getByRole("button",{name:"Gửi câu trả lời",exact:true}).click();
  await expect(page.locator("main").getByRole("alert")).toBeVisible();
  const saved=(await api(page,"/practice/history?limit=100")).data.items.filter((a:{student_answer:string})=>a.student_answer===answer);
  expect(saved).toHaveLength(1);
  await page.unroute("**/api/v1/practice/attempts");await page.reload();
  await expect(page.getByLabel("Câu trả lời",{exact:true})).toHaveValue(answer);
  const request=page.waitForRequest(r=>r.method()==="POST"&&r.url().endsWith("/practice/attempts"));
  await page.getByRole("button",{name:"Kiểm tra lại lần nộp",exact:true}).click();
  expect((await request).headers()["idempotency-key"]).toBe(key);
  await expect(page.getByTestId("practice-result")).toBeVisible();
  expect(new URL(page.url()).searchParams.get("attempt")).toBe(saved[0].id);
  const again=(await api(page,"/practice/history?limit=100")).data.items.filter((a:{student_answer:string})=>a.student_answer===answer);
  expect(again).toHaveLength(1);
  expect(again[0].medical_evaluation).toEqual(saved[0].medical_evaluation);
  fs.writeFileSync(root+"/browser-idempotency.json",JSON.stringify({commit_then_transport_failure:true,reload_restores_draft:true,same_idempotency_key:true,attempt_count:1,medical_unchanged:true},null,2));
});

test("public entry and authentication forms reflow and show field errors",async({page})=>{
  test.skip(before,"Baseline capture only");
  await connect(page);
  await capture(page,"public",{home:"/",login:"/login",register:"/register"});
  await page.goto(base+"/login");
  await page.getByLabel("Email",{exact:true}).fill("invalid-email");
  await page.getByLabel("Mật khẩu",{exact:true}).fill("UiFixtureOnly123!");
  await page.getByRole("button",{name:"Đăng nhập",exact:true}).click();
  await expect(page.locator("#email-error")).toHaveText("Địa chỉ email không hợp lệ.");
  await expect(page.locator("#auth-email")).toHaveAttribute("aria-invalid","true");
});
