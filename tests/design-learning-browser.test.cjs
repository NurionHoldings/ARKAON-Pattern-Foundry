const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {execFileSync}=require('node:child_process');
const {pathToFileURL}=require('node:url');
const run=(command,args)=>execFileSync(command,args,{cwd:process.cwd(),env:process.env,encoding:'utf8',stdio:'pipe'});
test('four original directions, selected sandbox CSS, actual computed feedback and touch selection',
 {skip:process.env.APF_RUN_BROWSER!=='1'},async()=>{
 const root=process.env.APF_DESIGN_EVIDENCE_DIR||fs.mkdtempSync(path.join(os.tmpdir(),'apf-design-'));
 fs.mkdirSync(root,{recursive:true});
 const python=process.env.APF_PYTHON||'python';
 for(const name of ['baseline','reference']){
   const ref=name==='reference';
   fs.writeFileSync(path.join(root,name+'.html'),`<!doctype html><html lang=ko><meta charset=utf-8><style>.content{display:grid;color:${ref?'#172033':'#aaa'};background:white;font:${ref?'18px/1.6':'12px/1.1'} system-ui;gap:${ref?24:2}px;width:280px}.content div{padding:8px}</style><div class=content><div>우리 사업의 가치를 전합니다.</div><div>서비스 안내와 문의를 확인하세요.</div></div></html>`);
 }
 fs.writeFileSync(path.join(root,'roles.json'),JSON.stringify([{role:'body',selector:'.content'}]));
 const capture=(html,out,css)=>run('node',['tools/capture-design-observation.cjs',path.join(root,html),path.join(root,'roles.json'),path.join(root,out),'390','http://localhost:8080/demo.html',...(css?[css]:[])]);
 capture('baseline.html','baseline.json');capture('reference.html','reference.json');
 const job={reference:JSON.parse(fs.readFileSync(path.join(root,'reference.json'))),baseline:JSON.parse(fs.readFileSync(path.join(root,'baseline.json'))),target_css:'services/demo.css'};
 fs.mkdirSync(path.join(root,'inbox/design-learning'),{recursive:true});
 fs.writeFileSync(path.join(root,'inbox/design-learning/job.json'),JSON.stringify(job));
 run(python,['-m','apf.design_learning','--foundry-root',root]);
 const dir=path.join(root,'state/design-learning');
 const filename=fs.readdirSync(dir).find(x=>x.endsWith('.json')&&x!=='latest.json');
 const bundle=JSON.parse(fs.readFileSync(path.join(dir,filename)));
 assert.equal(bundle.choices.length,4);
 for(const proposal of bundle.choices){
   const css=path.join(root,proposal.direction_id+'.css');fs.writeFileSync(css,proposal.candidate_css);
   capture('baseline.html',proposal.direction_id+'-after.json',css);
   const code=`import json;from apf.design_learning import evaluate;from pathlib import Path;p=Path(${JSON.stringify(root)});b=json.loads((p/'state/design-learning'/${JSON.stringify(filename)}).read_text());c=next(x for x in b['choices'] if x['direction_id']==${JSON.stringify(proposal.direction_id)});a=json.loads((p/${JSON.stringify(proposal.direction_id+'-after.json')}).read_text());r=evaluate(c,a,differentiation={'user_purpose':'읽기','original_composition':'자체 예시','beyond_color':'서체와 간격','evidence_ref':'synthetic-browser-run'});assert r['automated_check_passed'];assert not r['improvement_accepted'];(p/${JSON.stringify(proposal.direction_id+'-evaluation.json')}).write_text(json.dumps(r,ensure_ascii=False,indent=2))`;
   run(python,['-c',code]);
 }
 const {chromium}=require('playwright');
 const browser=await chromium.launch({headless:true,...(process.env.APF_CHROMIUM_EXECUTABLE?{executablePath:process.env.APF_CHROMIUM_EXECUTABLE}:{})});
 try{
  const page=await browser.newPage({viewport:{width:390,height:844},hasTouch:true});
  await page.goto(pathToFileURL(path.join(dir,filename.replace('.json','.html'))).href);
  assert.equal(await page.locator('button').count(),4);
  const download=page.waitForEvent('download');await page.locator('button').nth(2).click();
  const downloaded=await download;const selection=JSON.parse(fs.readFileSync(await downloaded.path(),'utf8'));
  assert.equal(selection.direction_id,'mobile');assert.equal(selection.proposal_digest,bundle.choices[2].proposal_digest);
  assert.equal(await page.locator('button[aria-pressed=true]').count(),1);
  await page.screenshot({path:path.join(root,'choices-mobile.png'),fullPage:true});
  fs.writeFileSync(path.join(root,'selection.json'),JSON.stringify(selection,null,2));
 }finally{await browser.close();}
 fs.writeFileSync(path.join(root,'browser-summary.json'),JSON.stringify({status:'PASS',directions:4,fixture_kind:'SYNTHETIC_NOT_EXTERNAL_LEARNING',improvement_accepted:false},null,2));
});
