/* Scoped before/after renderer measurements + an actual editor save/reopen journey. */
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {createHash}=require('node:crypto');
const {chromium}=require('playwright');
const {verifyCheckoutDir}=require('./brand-browser-git-verify.cjs');
const {verifyHarnessEntry}=require('./brand-browser-harness-guard.cjs');
const args=Object.fromEntries(process.argv.slice(2).reduce((a,v,i,s)=>i%2?a:[...a,[v.slice(2),s[i+1]]],[]));
for(const variant of ['baseline','candidate'])verifyCheckoutDir(args[variant+'-dir'],variant,args[variant+'-sha']);
verifyHarnessEntry(args['candidate-dir'],process.argv[1],'tools/test-brand-quality.cjs');
const out=path.resolve(args.out);fs.mkdirSync(out,{recursive:true});
const sha=x=>createHash('sha256').update(x).digest('hex');
const report={schema_version:'apf.brand-quality-comparison/v1',run_id:process.env.GITHUB_RUN_ID||'local',baseline_sha:args['baseline-sha'],candidate_sha:args['candidate-sha'],rows:[],files:[],journey:'NOT_RUN',implementation_actor:'ETERNIAN',arkaon_first_verification:'NOT_RUN',independent_audit:'NOT_RUN',improvement_accepted:false,merge_approved:false,production_apply_approved:false};
let browser,server;
(async()=>{try{
 browser=await chromium.launch();report.chromium=browser.version();
 const context=await browser.newContext(),page=await context.newPage();
 for(const variant of ['baseline','candidate']){
  const studio=require(path.resolve(args[variant+'-dir'],'services/brand-studio.js'));
  for(const width of [360,390])for(const accent of ['#ffffff','#fffffe','#e3c46d','#888888','#31594c','#000000'])for(const logoTone of ['light','dark','mono']){
   const brief={businessName:'햇살 에너지',industry:'태양광 시공',audience:'건물주',accent,logoTone,conceptId:'horizon',cardLayout:'company'};
   const copy=studio.suggestCopy(brief);const html=studio.render({...brief,...copy});
   await page.setViewportSize({width,height:900});await page.setContent(html);await page.evaluate(()=>document.fonts.ready);
   const metrics=await page.evaluate(()=>{
    const lum=c=>{const a=c.match(/[\d.]+/g).slice(0,3).map(Number).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;});return a[0]*.2126+a[1]*.7152+a[2]*.0722;};
    const ratio=(a,b)=>{const x=lum(a),y=lum(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);};
    const regions=['.logo','.front'].map(selector=>{
     const root=document.querySelector(selector),svg=root.querySelector('svg'),text=svg.querySelector('text');
     let surface=svg.parentElement;
     while(getComputedStyle(surface).backgroundColor==='rgba(0, 0, 0, 0)')surface=surface.parentElement;
     const foreground=getComputedStyle(text).fill,background=getComputedStyle(surface).backgroundColor;
     return {selector,foreground,background,ratio:ratio(foreground,background)};
    });
    return {regions,overflow:document.documentElement.scrollWidth>innerWidth+1};
   });
   const row={variant,width,accent,logoTone,brief_sha256:sha(JSON.stringify(brief)),render_sha256:sha(html),copy,...metrics};
   row.pass=metrics.regions.every(x=>x.ratio>=4.5)&&!metrics.overflow&&!/은\(는\)|을\(를\)/.test(copy.brandIntro+copy.tagline);
   if(accent==='#ffffff'&&logoTone==='light'){
    const name=`${variant}-white-${width}.png`,bytes=await page.screenshot({fullPage:true});fs.writeFileSync(path.join(out,name),bytes);report.files.push({path:name,sha256:sha(bytes)});
   }
   report.rows.push(row);
  }
 }
 await context.close();
 const root=path.resolve(args['candidate-dir']);
 server=http.createServer((req,res)=>{try{const file=path.resolve(root,'.'+new URL(req.url,'http://localhost').pathname);if(!file.startsWith(root+path.sep))throw Error();res.setHeader('Content-Type',({'.js':'text/javascript','.css':'text/css','.html':'text/html'})[path.extname(file)]||'text/plain');res.end(fs.readFileSync(file));}catch{res.writeHead(404);res.end();}});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const ctx=await browser.newContext({viewport:{width:390,height:900}}),p=await ctx.newPage();
 await p.goto(`http://127.0.0.1:${server.address().port}/services/logo-card.html`);
 await p.locator('#businessName').fill('햇살 에너지');await p.locator('#industry').fill('태양광 시공');await p.locator('#audience').fill('건물주');
 await p.locator('#accent').evaluate(el=>{el.value='#ffffff';el.dispatchEvent(new Event('input',{bubbles:true}));});await p.locator('#suggest-copy').click();await p.locator('#generate-concepts').click();
 const expected='태양광 시공 분야의 햇살 에너지입니다. 주요 고객은 건물주입니다.';
 if(await p.locator('#brandIntro').inputValue()!==expected)throw Error('generated copy mismatch');
 await p.locator('.concept').first().click();
 if(!/어두운 배경/.test(await p.locator('#contrast-guidance').innerText()))throw Error('missing contrast guidance');
 const swatches=await p.locator('.concept img').evaluateAll(imgs=>imgs.map(x=>getComputedStyle(x).backgroundColor));
 if(swatches.length!==6||swatches.some(x=>x!=='rgb(23, 43, 36)'))throw Error('unreadable candidate thumbnails');
 await p.locator('button[type=submit]').click();await p.getByRole('status').filter({hasText:'이 브라우저에 초안을 저장했습니다'}).waitFor();
 const second=await ctx.newPage();await second.goto(p.url());
 if(await second.locator('#accent').inputValue()!=='#ffffff'||await second.locator('#brandIntro').inputValue()!==expected)throw Error('save/reopen changed color or copy');
 report.journey='PASS';await ctx.close();
 report.status=report.rows.length===72&&report.rows.filter(x=>x.variant==='candidate').every(x=>x.pass)?'PASS':'FAIL';
}catch(e){report.status='FAIL';report.error=String(e.stack||e);}finally{
 if(browser)await browser.close();if(server)await new Promise(r=>server.close(r));
 report.baseline_failed=report.rows.filter(x=>x.variant==='baseline'&&!x.pass).length;report.candidate_failed=report.rows.filter(x=>x.variant==='candidate'&&!x.pass).length;
 fs.writeFileSync(path.join(out,'quality-manifest.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({status:report.status,rows:report.rows.length,baseline_failed:report.baseline_failed,candidate_failed:report.candidate_failed,journey:report.journey,error:report.error}));if(report.status!=='PASS')process.exitCode=1;
}})();
