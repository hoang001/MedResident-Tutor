import {test,expect,Page} from "@playwright/test";

// These UI contract tests replay synthetic responses. Live model verification
// is recorded separately and never inferred from this suite passing.
async function setup(page:Page,{fail=false,available=true}={}) {
 const calls={retrieve:0,propose:0,materialize:0,save:0,body:null as null|Record<string,unknown>};
 const evidence={source_unit_id:"retrieved-S",source_id:"synthetic-book",title:"Synthetic source",content:"Alpha requires condition A.",page_start:1,page_end:1};
 await page.addInitScript(()=>localStorage.setItem("access_token","synthetic-ui-test-token"));
 await page.route("**/api/v1/**",async route=>{
  const request=route.request(),path=new URL(request.url()).pathname.replace("/api/v1","");
  const respond=(json:unknown,status=200)=>route.fulfill({status,json,headers:{"Access-Control-Allow-Origin":"*"}});
  if(path==="/auth/me")return respond({id:"synthetic-admin",role:"ADMIN",full_name:"UI test admin"});
  if(path==="/admin/authoring/config")return respond({proposal_available:available,manual_authoring_available:true});
  if(path==="/admin/question-catalog")return respond({items:[],total:0,counts:{all:0,draft:0,published:0,review:0}});
  if(path==="/admin/source-catalog")return respond({items:[],total:0});
  if(path==="/knowledge/curriculum")return respond({nodes:[
   {id:"C7",type:"Course",title:"Chấn thương chỉnh hình chi trên",study_role:"focus",metadata:{course_code:"B21CN7"}},
   {id:"C8",type:"Course",title:"Chấn thương chỉnh hình chi dưới",study_role:"focus",metadata:{course_code:"B21CN8"}},
   {id:"C0",type:"Course",title:"Triết học",study_role:"prior_outcomes_only",metadata:{course_code:"C0"}},
  ]});
  if(path==="/admin/authoring/retrieve"){calls.retrieve++;return respond({bundle_token:"synthetic-bundle",evidence:[evidence],provenance:[],trace:{},status:"candidates_need_review"});}
  if(path==="/admin/authoring/propose"){
   calls.propose++;
   if(fail)return respond({error:{code:"AUTHORING_OUTPUT_INVALID",message:"Đề xuất không hợp lệ"}},502);
   return respond({reference_answer:"Alpha requires condition A.",criteria:[{description:"Nêu điều kiện A",max_score:1,source_unit_ids:["retrieved-S"]}],insufficient_basis:[],proposal_token:"synthetic-proposal"});
  }
  if(path==="/admin/authoring/materialize"){calls.materialize++;return respond([{...evidence,source_unit_id:"persisted-S",retrieval_id:"retrieved-S"}]);}
  if(path==="/admin/questions"&&request.method()==="POST"){
   calls.save++;calls.body=request.postDataJSON();
   return respond({...calls.body,question_id:"APP_Q_SYNTHETIC",version:1,is_available:false,criteria:(calls.body!.criteria as unknown[])},201);
  }
  return respond({});
 });
 await page.goto("/admin/questions");
 await page.getByRole("button",{name:"Tạo câu hỏi mới",exact:true}).click();
 return calls;
}

test("course suggestions open on focus, match accents/code, and select by keyboard",async({page})=>{
 await setup(page);
 const course=page.getByRole("combobox",{name:"Học phần",exact:true});
 await course.click();
 await expect(page.getByRole("listbox").getByRole("option")).toHaveCount(3);
 await course.fill("chan thuong");
 await expect(page.getByRole("listbox").getByRole("option")).toHaveCount(2);
 await course.fill("B21CN7");
 await expect(page.getByRole("listbox").getByRole("option")).toHaveCount(1);
 await course.press("ArrowDown");await course.press("Enter");
 await expect(course).toHaveValue("Chấn thương chỉnh hình chi trên");
 await expect(page.getByRole("listbox")).toHaveCount(0);
 await course.click();await expect(page.getByRole("listbox").getByRole("option")).toHaveCount(3);
 await course.press("Escape");await expect(page.getByRole("listbox")).toHaveCount(0);
});

test("AI preview writes nothing until explicit review and save; edited answer is kept",async({page})=>{
 const calls=await setup(page);
 await page.getByLabel("Nội dung câu hỏi",{exact:true}).fill("Synthetic alpha question?");
 await page.getByRole("button",{name:"Tìm nguồn và đề xuất đáp án",exact:true}).click();
 await expect(page.getByLabel("Đáp án tham khảo",{exact:true})).toHaveValue("Alpha requires condition A.");
 expect(calls.retrieve).toBe(1);expect(calls.propose).toBe(1);expect(calls.materialize).toBe(0);expect(calls.save).toBe(0);
 const save=page.getByRole("button",{name:"Duyệt và lưu nháp",exact:true});
 await expect(save).toBeDisabled();
 await page.getByLabel("Nội dung câu hỏi",{exact:true}).fill("Temporarily changed scope");
 await page.getByLabel("Nội dung câu hỏi",{exact:true}).fill("Synthetic alpha question?");
 await expect(save).toBeDisabled();
 const review=page.getByRole("checkbox",{name:/Tôi đã đối chiếu đáp án/});
 await review.check();await expect(save).toBeEnabled();
 await page.getByLabel("Đáp án tham khảo",{exact:true}).fill("Admin reviewed and edited answer.");
 await expect(review).not.toBeChecked();await expect(save).toBeDisabled();
 await review.check();await save.click();
 await expect(page.getByText("Đã lưu bản nháp. Lưu và phát hành là hai thao tác riêng.")).toBeVisible();
 expect(calls.materialize).toBe(1);expect(calls.save).toBe(1);
 expect(calls.body?.reference_answer).toBe("Admin reviewed and edited answer.");
 expect(calls.body?.proposal_reviewed).toBe(true);
 expect(calls.body?.proposal_token).toBe("synthetic-proposal");
 expect((calls.body?.criteria as {source_unit_ids:string[]}[])[0].source_unit_ids).toEqual(["persisted-S"]);
 await expect(page.getByRole("button",{name:"Phát hành câu hỏi",exact:true})).toBeDisabled();
});

test("failed proposal preserves question and does not save or retry",async({page})=>{
 const calls=await setup(page,{fail:true});
 await page.getByLabel("Nội dung câu hỏi",{exact:true}).fill("Keep this question");
 await page.getByRole("button",{name:"Tìm nguồn và đề xuất đáp án",exact:true}).click();
 await expect(page.getByRole("region",{name:"AI hỗ trợ biên soạn"}).getByRole("alert")).toContainText("AI chưa tạo được đề xuất hợp lệ");
 await expect(page.getByLabel("Nội dung câu hỏi",{exact:true})).toHaveValue("Keep this question");
 await expect(page.getByLabel("Đáp án tham khảo",{exact:true})).toHaveValue("");
 expect(calls.propose).toBe(1);expect(calls.materialize).toBe(0);expect(calls.save).toBe(0);
});

test("mobile suggestions remain visible and disabled AI permits manual drafting",async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await setup(page,{available:false});
 await page.getByRole("combobox",{name:"Học phần"}).click();
 await expect(page.getByRole("listbox").getByRole("option")).toHaveCount(3);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.getByRole("listbox").getByRole("option").first().click();
 await page.getByLabel("Nội dung câu hỏi",{exact:true}).fill("Manual draft");
 await expect(page.getByRole("button",{name:"Tìm nguồn và đề xuất đáp án",exact:true})).toBeDisabled();
 await expect(page.getByRole("button",{name:"Lưu bản nháp",exact:true})).toBeEnabled();
});
