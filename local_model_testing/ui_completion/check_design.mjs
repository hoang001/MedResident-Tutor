import fs from 'node:fs';
import {createRequire} from 'node:module';
const require=createRequire('/workspace/apps/frontend/package.json');
const yaml=require('js-yaml');
const text=fs.readFileSync('/workspace/DESIGN.md','utf8');
const tokens=yaml.load(text.match(/^---\r?\n([\s\S]*?)\r?\n---/)[1]);
const sidecar=JSON.parse(fs.readFileSync('/workspace/.impeccable/design.json','utf8'));
if(tokens.colors.navy!=='#142d4e'||tokens.colors.accent!=='#0b7779')throw Error('Wrong palette');
if(!tokens.typography.headline.fontFamily.includes('Source Sans 3'))throw Error('Wrong heading face');
if(sidecar.schemaVersion!==2)throw Error('Wrong sidecar schema');
for(const file of ['DESIGN.md','PRODUCT.md','.impeccable/design.json','docs/ui/design-system.md']){
  const content=fs.readFileSync('/workspace/'+file,'utf8');
  if(content.includes('\ufffd'))throw Error('Replacement characters in '+file);
  if(content.includes('?'))throw Error('Unexpected lossy text in '+file);
}
const guide=fs.readFileSync('/workspace/docs/ui/design-system.md','utf8');
if(!guide.includes('H\u1ec7 th\u1ed1ng giao di\u1ec7n'))throw Error('Missing Vietnamese heading');
const result={yaml_parsed:true,sidecar_json_parsed:true,navy_teal_tokens:true,heading_face:true,utf8_vietnamese:true};
fs.writeFileSync('/workspace/data/authoring/ui-completion-20261116/design-doc-checks.json',JSON.stringify(result,null,2));
console.log(result);
