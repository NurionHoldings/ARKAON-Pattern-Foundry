/* Real studio selection/save/reopen, isolated loopback only; no publishing. */
const fs=require('node:fs'),http=require('node:http'),path=require('node:path');
const {execFileSync}=require('node:child_process'),{createHash}=require('node:crypto');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),sha=execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim();
if(sha!==process.env.CANDIDATE_SHA||execFileSync('git',['status','--porcelain'],{cwd:root,encoding:'utf8'}).trim())throw Error('Clean, exact candidate SHA required');
const out=path.resolve(process.env.EVIDENCE_OUT);fs.mkdirSync(out,{recursive:true});
const digest=b=>createHash('sha256').update(b).digest('hex');
const report={schema_version:'apf.platform-foundation-browser/v1',tested_head:sha,run_id:process.env.GITHUB_RUN_ID,rows:[],errors:[],implementation_actor:'ETERNIAN',arkaon_first_verification:'NOT_RUN',independent_audit:'NOT_RUN',improvement_accepted:false,merge_approved:false,production_apply_approved:false};
const server=http.createServer((req,res)=>{try{const f=path.resolve(root,'.'+new URL(req.url,'http://localhost').pathname);if(!f.startsWith(root+path.sep))throw Error();res.setHeader('Content-Type',({'.js':'text/javascript','.css':'text/css','.html':'text/html'})[path.extname(f)]||'text/plain');res.end(fs.readFileSync(f));}catch{res.writeHead(404);res.end();}});
let browser;
(async()=>{try{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));browser=await chromium.launch();report.chromium=browser.version();
 for(const id of ['dapanda','arirang'])for(const width of [360,390,1440]){
  const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage();
  page.on('pageerror',e=>report.errors.push(e.message));
  await page.goto(`http://127.0.0.1:${server.address().port}/services/site-builder.html`);
  await page.locator('#title').fill('햇살 에너지');await page.locator('#audience').fill('지역 건물주');await page.locator('#story').fill('설치 조건을 확인하고 계획을 함께 정리합니다.');
  await page.locator('[data-step="1"]').click();await page.locator(`[data-theme="${id}"]`).click();
  await page.locator('[data-step="2"]').click();await page.locator('#offerings').fill('설치 상담 | 현장 조건과 범위 확인\n설계 검토 | 도면과 예상 일정 확인\n점검 안내 | 필요한 확인사항 정리');await page.locator('#difference').fill('조건을 쉽게 설명합니다.');await page.locator('#process').fill('요청 확인\n범위 협의\n결과 검토');await page.locator('#contact').fill('연락 방법 확인 필요');
  await page.locator('#save').click();await page.getByRole('status').filter({hasText:'초안을 저장했습니다'}).waitFor();
  const saved=page.url(),second=await context.newPage();await second.goto(saved);await second.locator('#title').waitFor();
  await second.waitForFunction(()=>document.querySelector('#title').value==='햇살 에너지');
  if(await second.locator(`[data-theme="${id}"]`).getAttribute('aria-pressed')!=='true')throw Error('preset not restored');
  if(await second.locator('#story').inputValue()!=='설치 조건을 확인하고 계획을 함께 정리합니다.')throw Error('content not restored');
  const frame=second.frameLocator('#preview');await frame.locator('body.'+id).waitFor();
  const metrics=await frame.locator('body').evaluate(body=>({background:getComputedStyle(body).backgroundColor,overflow:body.ownerDocument.documentElement.scrollWidth>body.ownerDocument.defaultView.innerWidth+1,columns:getComputedStyle(body.querySelector('.offers')).gridTemplateColumns,theme:body.className,hero:getComputedStyle(body.querySelector('.hero')).backgroundImage}));
  const outer=await second.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);
  await second.locator('#preview').scrollIntoViewIfNeeded();await frame.locator('body').evaluate(body=>body.ownerDocument.fonts.ready);
  const png=await second.locator('#preview').screenshot(),name=`${id}-${width}.png`;fs.writeFileSync(path.join(out,name),png);
  const expected=id==='dapanda'?'rgb(11, 11, 10)':'rgb(243, 246, 252)';
  const ok=metrics.background===expected&&!metrics.overflow&&!outer;
  report.rows.push({preset:id,width,...metrics,outer_overflow:outer,save_reopen:'PASS',status:ok?'PASS':'FAIL',screenshot:{path:name,sha256:digest(png)}});
  await context.close();
 }
 report.status=report.rows.length===6&&report.rows.every(x=>x.status==='PASS')&&!report.errors.length?'PASS':'FAIL';
}catch(e){report.status='FAIL';report.error=String(e.stack||e);}finally{if(browser)await browser.close();await new Promise(r=>server.close(r));fs.writeFileSync(path.join(out,'manifest.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({status:report.status,rows:report.rows.length,error:report.error}));if(report.status!=='PASS')process.exitCode=1;}})();
