/* Review-only: immutable target checkout; finding presence is not execution failure. */
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {execFileSync}=require('node:child_process'),{createHash}=require('node:crypto');
const {chromium}=require('playwright');
const [targetDir,targetSha,outputDir]=process.argv.slice(2);
if(!targetDir||!/^[a-f0-9]{40}$/.test(targetSha||'')||!outputDir)throw Error('Usage: target-dir target-sha output-dir');
const root=path.resolve(targetDir),out=path.resolve(outputDir);fs.mkdirSync(out,{recursive:true});
if(execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim()!==targetSha)throw Error('Target SHA mismatch');
if(execFileSync('git',['status','--porcelain'],{cwd:root,encoding:'utf8'}).trim())throw Error('Target not clean');
const studio=require(path.join(root,'services/brand-studio.js'));
const sha=v=>createHash('sha256').update(v).digest('hex');
const manifest={schema_version:'apf.brand-visual-usability-review/v1',target_commit:targetSha,review_harness_commit:process.env.GITHUB_SHA||null,ci_run_id:process.env.GITHUB_RUN_ID||null,executed_at:new Date().toISOString(),source_hashes:{},matrix:[],journey:{},findings:[],execution_status:'RUNNING',visual_review_status:'PENDING',independent_audit_status:'NOT_COMPLETED',improvement_accepted:false,merge_approved:false,production_apply_approved:false};
for(const name of ['brand-studio.js','brand-concepts.js','brand-editing.js','brand-studio.css'])manifest.source_hashes[name]=sha(fs.readFileSync(path.join(root,'services',name)));
const cases=[];
for(const conceptId of ['horizon','bridge','facet','bloom','route','signal'])for(const logoLockup of ['horizontal','stacked','symbol'])for(const logoTone of ['light','dark','mono'])for(const cardLayout of ['company','personal']){
 const index=cases.length,brief=index%3;
 cases.push({id:'case-'+index,width:390,raw:{businessName:['햇살 에너지','동네 작은 카페','가나다라마바사아자차카타파하'.repeat(5).slice(0,60)][brief],industry:['태양광 시공','카페','개인 디자이너'][brief],audience:'소상공인',services:'상담\n맞춤 구성',strengths:'이해하기 쉬운 설명',initials:'ON',person:'가상 담당',role:'담당',email:'test@example.com',website:'https://example.com',address:'시험용 가상 주소',tagline:'사업의 이야기를 쉽게 전합니다',brandIntro:'사업 소개를 읽고 로고와 명함에 같은 정보를 반영하는 가상 시험입니다.',conceptId,logoLockup,logoTone,cardLayout,accent:'#31594c',sample:true}});
}
for(const width of [360,768,1440])cases.push({id:'boundary-'+width,width,raw:{...cases[0].raw,businessName:'가나다라마바사아자차카타파하'.repeat(5).slice(0,60),symbolSize:100,logoGap:64,letterSpacing:4,logoAlign:'right'}});
cases.push({id:'white-on-white',width:390,raw:{...cases[0].raw,accent:'#ffffff',logoTone:'light'}});
const byId=new Map(cases.map(c=>[c.id,c]));
const server=http.createServer((req,res)=>{
 try{
  const url=new URL(req.url,'http://localhost');
  if(url.pathname.startsWith('/case/')){const c=byId.get(url.pathname.slice(6));if(!c){res.writeHead(404);return res.end();}res.setHeader('Content-Type','text/html;charset=utf-8');return res.end(studio.render(c.raw));}
  const file=path.resolve(root,'.'+decodeURIComponent(url.pathname));
  if(!file.startsWith(root+path.sep)||!fs.statSync(file).isFile()){res.writeHead(404);return res.end();}
  res.setHeader('Content-Type',({'.js':'text/javascript','.html':'text/html','.css':'text/css'}[path.extname(file)]||'text/plain')+';charset=utf-8');res.end(fs.readFileSync(file));
 }catch{res.writeHead(404);res.end();}
});
async function saveScreenshot(page,name){const bytes=await page.screenshot({fullPage:true});fs.writeFileSync(path.join(out,name),bytes);return {path:name,sha256:sha(bytes)};}
async function values(page){return page.locator('#brand').evaluate(form=>({values:Object.fromEntries([...form.querySelectorAll('input,select,textarea')].filter(x=>x.id).map(x=>[x.id,x.value])),sample:form.dataset.sample}));}
async function outputReady(page){await page.frameLocator('#preview').locator('svg').first().waitFor();await page.locator('#preview').scrollIntoViewIfNeeded();await page.frameLocator('#preview').locator('svg').first().evaluate(async svg=>{await svg.ownerDocument.fonts.ready;});}
(async()=>{let browser;
 try{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const origin=`http://127.0.0.1:${server.address().port}`;
  browser=await chromium.launch({headless:true});manifest.browser=browser.version();
  for(const c of cases){
   const context=await browser.newContext({viewport:{width:c.width,height:1000}}),page=await context.newPage();
   await page.goto(origin+'/case/'+c.id);await page.evaluate(()=>document.fonts.ready);
   const metrics=await page.evaluate(()=>{
    const problems=[],root=document.documentElement;
    if(root.scrollWidth>innerWidth+1)problems.push('horizontal-overflow');
    for(const svg of document.querySelectorAll('svg')){
     const box=svg.getBoundingClientRect();
     for(const text of svg.querySelectorAll('text')){const r=text.getBoundingClientRect();if(r.left<box.left-1||r.right>box.right+1||r.top<box.top-1||r.bottom>box.bottom+1)problems.push('svg-text-bounds');}
    }
    const first=document.querySelector('.logo');
    return {problems,logoBackground:getComputedStyle(first).backgroundColor,firstLogoColors:[...first.querySelectorAll('text')].map(x=>getComputedStyle(x).fill),bodyText:document.body.innerText};
   });
   const screenshot=await saveScreenshot(page,c.id+'.png');
   manifest.matrix.push({id:c.id,width:c.width,brief_digest:sha(JSON.stringify(c.raw)),raw:c.raw,...metrics,screenshot});
   await context.close();
  }
  const context=await browser.newContext({viewport:{width:390,height:900}}),page=await context.newPage();
  const runtime=[];page.on('pageerror',e=>runtime.push(e.message));await page.goto(origin+'/services/logo-card.html');
  const start=performance.now();
  for(const [id,value] of Object.entries({industry:'태양광 시공',audience:'건물주',services:'설치 조건 상담\n시공 범위 안내',strengths:'조건을 쉽게 설명',businessName:'햇살 에너지',person:'가상 담당',email:'test@example.com'}))await page.locator('#'+id).fill(value);
  await page.getByRole('button',{name:'사업 정보로 문구 제안 (빈 칸만)',exact:true}).click();
  manifest.journey.first_copy={tagline:await page.locator('#tagline').inputValue(),intro:await page.locator('#brandIntro').inputValue(),time_ms:performance.now()-start};
  await page.getByRole('button',{name:'사업 정보로 디자인 방향 6개 비교',exact:true}).click();
  await page.locator('.concept').filter({hasText:'지평선'}).focus();await page.keyboard.press('Enter');
  manifest.journey.keyboard_concept=await page.locator('#conceptId').inputValue();
  await page.locator('#symbolSize').focus();const before=await page.locator('#symbolSize').inputValue();await page.keyboard.press('ArrowUp');
  manifest.journey.keyboard_number={before,after:await page.locator('#symbolSize').inputValue()};
  await page.locator('#tagline').fill('사용자가 직접 고친 문구');
  const original=await values(page);await page.getByRole('button',{name:'초안 저장 · 이어서 편집',exact:true}).click();await page.getByRole('status').filter({hasText:'초안을 저장했습니다'}).waitFor();
  const reopen=await context.newPage();await reopen.goto(page.url());await outputReady(reopen);
  const restored=await values(reopen);manifest.journey.save_restore={same:JSON.stringify(original)===JSON.stringify(restored),original,restored};
  // Fault injection applies only to disposable browser context and only one project save.
  await reopen.evaluate(()=>{const saved=Storage.prototype.setItem;let once=true;Storage.prototype.setItem=function(k,v){if(once&&k==='apf.home.projects.v1'){once=false;throw new DOMException('Test quota fault','QuotaExceededError');}return saved.call(this,k,v);};});
  await reopen.locator('#brandIntro').fill('저장 실패에도 보존해야 하는 사용자 문구');const beforeFailure=await values(reopen);
  await reopen.getByRole('button',{name:'초안 저장 · 이어서 편집',exact:true}).click();
  manifest.journey.save_failure={message:await reopen.getByRole('status').textContent(),input_preserved:JSON.stringify(beforeFailure)===JSON.stringify(await values(reopen))};
  await reopen.getByRole('button',{name:'초안 저장 · 이어서 편집',exact:true}).click();
  manifest.journey.retry_message=await reopen.getByRole('status').textContent();
  await context.setOffline(true);await reopen.locator('#tagline').fill('오프라인에서도 작성한 문구');await reopen.getByRole('button',{name:'초안 저장 · 이어서 편집',exact:true}).click();
  manifest.journey.offline_save_message=await reopen.getByRole('status').textContent();await context.setOffline(false);
  await outputReady(reopen);manifest.journey.screenshot=await saveScreenshot(reopen,'journey-editor.png');
  const result=await reopen.locator('#preview').screenshot();fs.writeFileSync(path.join(out,'journey-result.png'),result);manifest.journey.result_screenshot={path:'journey-result.png',sha256:sha(result)};
  manifest.journey.runtime_errors=runtime;await context.close();manifest.execution_status='COMPLETE';
 }catch(error){manifest.execution_status='ERROR';manifest.execution_error=String(error.stack||error);process.exitCode=1;}
 finally{if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));fs.writeFileSync(path.join(out,'visual-review-manifest.json'),JSON.stringify(manifest,null,2)+'\n');console.log(JSON.stringify({execution:manifest.execution_status,matrix_rows:manifest.matrix.length,journey:manifest.journey.save_restore?.same,error:manifest.execution_error}));}
})();
