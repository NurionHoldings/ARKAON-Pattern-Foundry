const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
test('12 gallery samples -> shortlist -> editor -> saved edit and gallery return', {skip:process.env.APF_RUN_BROWSER!=='1',timeout:150000}, async()=>{
 const {chromium}=require('playwright');const root=path.resolve(__dirname,'..');
 const server=http.createServer((req,res)=>{try{const file=path.resolve(root,'.'+new URL(req.url,'http://localhost').pathname);if(!file.startsWith(root+path.sep))throw Error();const content=fs.readFileSync(file);res.setHeader('Content-Type',({'.html':'text/html','.js':'text/javascript','.css':'text/css'}[path.extname(file)]||'text/plain')+'; charset=utf-8');res.end(content);}catch{res.writeHead(404);res.end();}});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const origin='http://127.0.0.1:'+server.address().port;
 const browser=await chromium.launch({headless:true});const context=await browser.newContext();
 const out=process.env.APF_GALLERY_EVIDENCE_DIR||'/tmp/brand-gallery-evidence';fs.mkdirSync(out,{recursive:true});
 try{
 const page=await context.newPage();await page.setViewportSize({width:390,height:844});await page.goto(origin+'/services/brand-gallery.html');
 await page.locator('#businessName').fill('햇살과 함께하는 태양광');await page.locator('#industry').fill('태양광');await page.locator('#tagline').fill('직접 다듬은 문구');await page.locator('#brandIntro').fill('내가 제공하는 서비스만 기록합니다.');await page.getByRole('button',{name:'내 정보로 견본 보기',exact:true}).click();
 assert.equal(await page.locator('.sample').count(),12);
 assert.equal(await page.locator('[data-choose]:enabled').count(),0);
 const hashes=[];for(let i=0;i<12;i++){const article=page.locator('.sample').nth(i);await article.scrollIntoViewIfNeeded();const frame=await (await article.locator('iframe').elementHandle()).contentFrame();await frame.locator('.front').waitFor();assert.ok((await frame.locator('body').innerText()).includes('직접 다듬은 문구'));const src=await article.locator('img').getAttribute('src');hashes.push(require('node:crypto').createHash('sha256').update(src).digest('hex'));if(i===0||i===6||i===11)await article.screenshot({path:path.join(out,`sample-${i+1}-390.png`)});}
 assert.equal(new Set(hashes).size,12);
 for(let i=0;i<3;i++)await page.locator('[data-shortlist]').nth(i).click();
 const chosen=await page.locator('[data-choose]').nth(1).getAttribute('data-choose');await page.locator('[data-choose]').nth(1).click();
 assert.equal(await page.locator('[data-choose][aria-pressed=true]').count(),1);
 await page.getByRole('button',{name:'선택한 안의 내용·디자인 다듬기',exact:true}).click();await page.waitForURL('**/logo-card.html?project=*');
 const projectUrl=page.url();assert.equal(await page.locator('#conceptId').inputValue(),chosen);assert.equal(await page.locator('#tagline').inputValue(),'직접 다듬은 문구');
 await page.locator('#brandIntro').fill('심화 편집 후에도 보존할 소개');await page.locator('#phone').fill('010-0000-0000');await page.getByRole('button',{name:'초안 저장 · 이어서 편집',exact:true}).click();
 const reopened=await context.newPage();await reopened.goto(projectUrl);assert.equal(await reopened.locator('#brandIntro').inputValue(),'심화 편집 후에도 보존할 소개');assert.equal(await reopened.locator('#conceptId').inputValue(),chosen);
 await reopened.locator('#gallery-link').click();await reopened.waitForURL('**/brand-gallery.html?project=*');assert.equal(await reopened.locator('#brandIntro').inputValue(),'심화 편집 후에도 보존할 소개');
 assert.equal(await reopened.locator('[data-shortlist][aria-pressed=true]').count(),3);
 for(const width of [360,390,768,1440]){await reopened.setViewportSize({width,height:900});const overflow=await reopened.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);assert.equal(overflow,false,`overflow ${width}`);await reopened.screenshot({path:path.join(out,`gallery-${width}.png`),fullPage:true});}
 fs.writeFileSync(path.join(out,'summary.json'),JSON.stringify({status:'PASS',samples:12,unique_logo_previews:12,shortlist:3,selected:chosen,save_reopen:'PASS',editor_to_gallery:'PASS',viewports:[360,390,768,1440],fixture_kind:'SYNTHETIC',improvement_accepted:false},null,2));
 }finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
});
