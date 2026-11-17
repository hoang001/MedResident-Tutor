// Review-only contact sheets; no images or assets in the application are modified.
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
const require=createRequire('/workspace/apps/frontend/package.json');
const {chromium}=require('@playwright/test');
const root='/workspace/data/authoring/ui-completion-20261116';
const browser=await chromium.launch({headless:true});
const page=await browser.newPage();
for(const prefix of ['before','after']){
 const files=fs.readdirSync(root).filter(name=>name.startsWith(prefix+'-')&&name.endsWith('.png')).sort();
 for(let i=0;i<files.length;i+=6){
  const rows=files.slice(i,i+6).map(name=>({name,data:'data:image/png;base64,'+fs.readFileSync(path.join(root,name)).toString('base64')}));
  const png=await page.evaluate(async rows=>{
   const canvas=document.createElement('canvas');canvas.width=1600;canvas.height=Math.ceil(rows.length/2)*550;
   const c=canvas.getContext('2d');c.fillStyle='#e2e7ef';c.fillRect(0,0,canvas.width,canvas.height);
   for(let n=0;n<rows.length;n++){
    const img=new Image();img.src=rows[n].data;await img.decode();
    const x=(n%2)*800,y=Math.floor(n/2)*550;
    c.fillStyle='#142d4e';c.font='16px Arial';c.fillText(rows[n].name,x+10,y+24);
    // The full page at right verifies capture validity; the first viewport at left supports layout review.
    const scale=Math.min(580/img.width,500/Math.min(img.height,1000));
    c.drawImage(img,0,0,img.width,Math.min(img.height,1000),x+10,y+40,img.width*scale,Math.min(img.height,1000)*scale);
    const fullScale=Math.min(190/img.width,500/img.height);
    c.drawImage(img,x+600,y+40,img.width*fullScale,img.height*fullScale);
   }
   return canvas.toDataURL('image/png').split(',')[1];
  },rows);
  fs.writeFileSync(path.join(root,`gallery-${prefix}-${Math.floor(i/6)+1}.png`),Buffer.from(png,'base64'));
 }
}
await browser.close();
