/* Browser regression only; no production service, accounts or external network. */
const fs=require('node:fs'),http=require('node:http'),path=require('node:path');
const {createHash}=require('node:crypto');
const {chromium}=require('playwright');
const args=Object.fromEntries(process.argv.slice(2).reduce((a,v,i,s)=>i%2?a:[...a,[v.replace(/^--/,''),s[i+1]]],[]));
for(const key of ['baseline-dir','candidate-dir','baseline-sha','candidate-sha','out'])if(!args[key])throw Error(`Missing --${key}`);
for(const key of ['baseline-sha','candidate-sha'])if(!/^[0-9a-f]{40}$/.test(args[key]))throw Error('Full SHA required');
const out=path.resolve(args.out);fs.mkdirSync(out,{recursive:true});
const sha=v=>createHash('sha256').update(v).digest('hex');
const fixtures=[
 {businessName:'햇살 에너지',industry:'태양광 시공',audience:'건물주',services:'설치 조건 상담\n시공 범위 안내',strengths:'조건을 쉽게 설명',person:'가상 담당',email:'solar@example.com'},
 {businessName:'동네 작은 카페',industry:'카페',audience:'동네 주민',services:'커피\n브런치',strengths:'편안한 공간',person:'가상 담당',email:'cafe@example.com'},
 {businessName:'가나다라마바사아자차카타파하'.repeat(5).slice(0,60),industry:'개인 디자이너',audience:'소상공인',services:'브랜드 기획\n시각 디자인',strengths:'이해하기 쉬운 설명',person:'가상 담당',email:'design@example.com'},
].map(x=>({...x,initials:'ON',tagline:'가상 사업 소개',brandIntro:'입력한 사업 사실을 바탕으로 편집하는 시험용 소개입니다.',role:'담당',phone:'',website:'https://example.com',address:'시험용 가상 주소'}));
async function serve(dir){
 const root=path.resolve(dir),server=http.createServer((req,res)=>{
  try{
   const file=path.resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname));
   if(!file.startsWith(root+path.sep)||!fs.statSync(file).isFile()){res.writeHead(404);return res.end();}
   const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css'}[path.extname(file)]||'application/octet-stream';
   res.writeHead(200,{'Content-Type':mime+';charset=utf-8'});res.end(fs.readFileSync(file));
  }catch{res.writeHead(404);res.end();}
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 return {server,url:`http://127.0.0.1:${server.address().port}/services/logo-card.html`};
}
async function settle(page){
 await page.frameLocator('#preview').locator('svg').first().waitFor();
 await page.locator('#preview').evaluate(async frame=>{await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));});
}
async function inspect(page){
 const outer=await page.evaluate(()=>({viewport:innerWidth,scroll:document.documentElement.scrollWidth,client:document.documentElement.clientWidth}));
 const frame=page.frameLocator('#preview');
 const inner=await frame.locator('body').evaluate(body=>{
  const doc=body.ownerDocument,win=doc.defaultView,issues=[];
  if(doc.documentElement.scrollWidth>win.innerWidth+1)issues.push('iframe-horizontal-overflow');
  for(const svg of doc.querySelectorAll('svg')){
   const box=svg.getBoundingClientRect();
   const texts=[...svg.querySelectorAll(':scope > text')];
   const rects=texts.map(t=>t.getBoundingClientRect());
   for(const r of rects)if(r.left<box.left-1||r.right>box.right+1||r.top<box.top-1||r.bottom>box.bottom+1)issues.push('svg-text-outside-viewbox');
   for(let i=1;i<rects.length;i++)if(rects[i].top<rects[i-1].bottom-1)issues.push('svg-text-line-overlap');
  }
  return {width:win.innerWidth,scroll:doc.documentElement.scrollWidth,issues,text:body.innerText};
 });
 if(outer.scroll>outer.client+1)inner.issues.push('editor-horizontal-overflow');
 return {outer,inner};
}
async function fill(page,brief){
 await page.getByRole('button',{name:'가상 예시로 살펴보기',exact:true}).click();
 for(const [key,value] of Object.entries(brief))await page.locator('#'+key).fill(value);
 await page.getByRole('button',{name:'사업 정보로 디자인 방향 6개 비교',exact:true}).click();
 await page.locator('.concept').filter({hasText:'지평선'}).click();
 await settle(page);
}
async function controls(page){return page.evaluate(()=>Object.fromEntries(['symbolSize','logoGap','letterSpacing','logoAlign','businessName','tagline','person'].map(k=>[k,document.getElementById(k).value])));}
async function svg(page){await settle(page);return page.frameLocator('#preview').locator('svg').first().evaluate(el=>el.outerHTML);}
(async()=>{
 const manifest={schema_version:'apf.brand-browser-regression/v1',created_at:new Date().toISOString(),baseline_commit:args['baseline-sha'],candidate_commit:args['candidate-sha'],contributor:'ETERNIAN_TEST_HARNESS',arkaon_first_verification:'NOT_RUN',independent_audit_status:'NOT_RUN',visual_human_review:'NOT_RUN',improvement_accepted:false,measurements:[],browser_undo_redo:'NOT_RUN',browser_save_reopen:'NOT_RUN',ci_run_id:process.env.GITHUB_RUN_ID||null,limits:['Chromium desktop viewport emulation; no physical mobile device','DOM overflow/text bounds checks do not establish design quality or all possible overlaps']};
 const servers=[],errors=[];let browser;
 try{
  const base=await serve(args['baseline-dir']),candidate=await serve(args['candidate-dir']);servers.push(base.server,candidate.server);
  manifest.local_preview_url=candidate.url;
  browser=await chromium.launch({headless:true});manifest.browser_version=browser.version();
  for(let i=0;i<fixtures.length;i++)for(const width of [360,390,768,1440])for(const [name,site] of [['baseline',base],['candidate',candidate]]){
   const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage();
   page.on('pageerror',e=>errors.push({scope:name,brief:i+1,width,error:e.message}));
   await page.goto(site.url,{waitUntil:'load'});await fill(page,fixtures[i]);
   const formValues=await page.locator('#brand').evaluate(form=>Object.fromEntries([...form.querySelectorAll('input,textarea,select')].filter(e=>e.id).map(e=>[e.id,e.value])));
   const measurement=await inspect(page),prefix=`brief-${i+1}-${width}-${name}`;
   await page.locator('#preview').scrollIntoViewIfNeeded();
   await page.frameLocator('#preview').locator('svg').first().evaluate(async el=>{await el.ownerDocument.fonts.ready;});
   const resultScreenshot=await page.locator('#preview').screenshot();fs.writeFileSync(path.join(out,prefix+'-result.png'),resultScreenshot);
   const screenshot=await page.screenshot({fullPage:true});fs.writeFileSync(path.join(out,prefix+'.png'),screenshot);
   const dom=await page.content();fs.writeFileSync(path.join(out,prefix+'.html'),dom);
   const rendered=await page.frameLocator('#preview').locator('html').evaluate(el=>el.outerHTML);fs.writeFileSync(path.join(out,prefix+'-result.html'),rendered);
   const {text,...inner}=measurement.inner;
   manifest.measurements.push({brief:i+1,brief_digest:sha(JSON.stringify(fixtures[i])),width,variant:name,form_values:formValues,outer:measurement.outer,inner,issues:inner.issues,status:inner.issues.length?'FAIL':'PASS',screenshot:{path:prefix+'.png',sha256:sha(screenshot)},result_screenshot:{path:prefix+'-result.png',sha256:sha(resultScreenshot)},dom:{path:prefix+'.html',sha256:sha(dom)},rendered_html:{path:prefix+'-result.html',sha256:sha(rendered)}});
   await context.close();
  }
  const context=await browser.newContext({viewport:{width:390,height:900}}),page=await context.newPage();
  await page.goto(candidate.url);await fill(page,fixtures[0]);
  await page.locator('#logoGap').fill('30');await page.locator('#letterSpacing').fill('2');await page.locator('#logoAlign').selectOption('right');
  const initial=await controls(page),initialSvg=sha(await svg(page));
  for(let i=0;i<10;i++)await page.locator('#symbolSize').fill(String(41+i*5));
  const final=await controls(page),finalSvg=sha(await svg(page));
  for(let i=0;i<10;i++)await page.getByRole('button',{name:'실행 취소',exact:true}).click();
  const undone=await controls(page),undoneSvg=sha(await svg(page));
  for(let i=0;i<10;i++)await page.getByRole('button',{name:'다시 실행',exact:true}).click();
  const redone=await controls(page),redoneSvg=sha(await svg(page));
  const undoPass=JSON.stringify(initial)===JSON.stringify(undone)&&initialSvg===undoneSvg;
  const redoPass=JSON.stringify(final)===JSON.stringify(redone)&&finalSvg===redoneSvg;
  manifest.browser_undo_redo=undoPass&&redoPass?'PASS':'FAIL';
  manifest.undo_redo_evidence={initial,final,undone,redone,initialSvg,finalSvg,undoneSvg,redoneSvg};
  await page.getByRole('button',{name:'초안 저장 · 이어서 편집',exact:true}).click();
  await page.getByRole('status').filter({hasText:'이 브라우저에 초안을 저장했습니다'}).waitFor();
  const saved=page.url(),second=await context.newPage();await second.goto(saved);const restored=await controls(second),restoredSvg=sha(await svg(second));
  manifest.browser_save_reopen=JSON.stringify(restored)===JSON.stringify(final)&&restoredSvg===finalSvg?'PASS':'FAIL';
  manifest.save_reopen_evidence={url:saved,restored,restoredSvg};
  await context.close();
 }catch(error){manifest.execution_error=String(error.stack||error);}
 finally{
  if(browser)await browser.close();for(const server of servers)await new Promise(resolve=>server.close(resolve));
  manifest.runtime_errors=errors;
  const candidateRows=manifest.measurements.filter(x=>x.variant==='candidate');
  manifest.browser_12_condition_comparison=candidateRows.length===12&&candidateRows.every(x=>x.status==='PASS')?'PASS':'FAIL';
  const passed=!manifest.execution_error&&!errors.length&&manifest.browser_12_condition_comparison==='PASS'&&manifest.browser_undo_redo==='PASS'&&manifest.browser_save_reopen==='PASS';
  manifest.status=passed?'PASS':'FAIL';
  fs.writeFileSync(path.join(out,'browser-manifest.json'),JSON.stringify(manifest,null,2)+'\n');
  console.log(JSON.stringify({status:manifest.status,conditions:manifest.measurements.length,undo_redo:manifest.browser_undo_redo,save_reopen:manifest.browser_save_reopen,error:manifest.execution_error}));
  if(!passed)process.exitCode=1;
 }
})();
