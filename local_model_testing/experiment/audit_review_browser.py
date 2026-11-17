"""Inspect the generated local research review with Chromium; no API/model requests."""
import json
import subprocess

from local_model_testing.launch import DOCKER

from .common import ROOT, RUN, write

SCRIPT = r'''
const {chromium} = require('@playwright/test');
(async () => {
 const browser=await chromium.launch({headless:true});
 try {
  const page=await browser.newPage({viewport:{width:1280,height:900}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('file:///workspace/data/evaluation/runs/benchmark-v1-20261110/review.html');
  const articles=await page.locator('article').count();
  if(articles!==50)throw new Error('Expected50originalquestions');
  const target=page.locator('article#MRB1_03_01');
  await target.locator('details').first().locator('summary').first().click();
  await target.scrollIntoViewIfNeeded();
  await page.screenshot({path:'/workspace/data/evaluation/runs/benchmark-v1-20261110/review-desktop.png'});
  await page.setViewportSize({width:390,height:844});
  await target.scrollIntoViewIfNeeded();
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
  await page.screenshot({path:'/workspace/data/evaluation/runs/benchmark-v1-20261110/review-mobile.png'});
  if(overflow||errors.length)throw new Error(JSON.stringify({overflow,errors}));
  console.log(JSON.stringify({articles,script_errors:errors.length,mobile_horizontal_overflow:overflow,model_calls:0}));
 } finally {await browser.close();}
})();
'''


def main():
    cmd = [str(DOCKER), "run", "--rm", "-i", "--name", "medresident-experiment-review-browser",
        "--network", "none", "--mount", "type=bind,source="+str(ROOT)+",target=/workspace",
        "--mount", "type=volume,source=medresident-web-node-modules,target=/workspace/apps/frontend/node_modules",
        "-w", "/workspace/apps/frontend", "mcr.microsoft.com/playwright:v1.56.1-noble", "node", "-"]
    result = subprocess.check_output(cmd, input=SCRIPT.encode())
    report = json.loads(result)
    write(RUN / "review-browser-check.json", report)
    print(json.dumps(report))


if __name__ == "__main__":
    main()
