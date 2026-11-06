// Captures a previously collected, local HTML archive in an offline browser.
// It neither fetches external websites nor imports external CSS/assets into products.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const hash = b => crypto.createHash('sha256').update(b).digest('hex');
async function main() {
  const [html, mapping, output, widthArg='390', sourceUrl='http://localhost:8080/demo.html', css] = process.argv.slice(2);
  if (!html || !mapping || !output) throw Error('html roles.json output.json [width] [sourceURL] [candidate.css]');
  const width = Number(widthArg);
  if (!Number.isInteger(width) || width < 240 || width > 8192) throw Error('invalid viewport');
  const roles = JSON.parse(fs.readFileSync(mapping,'utf8'));
  if (!Array.isArray(roles) || !roles.length || roles.length > 100 || roles.some(r=>!/^\.[\w-]+$|^#[\w-]+$/.test(r.selector))) throw Error('simple role selectors required');
  const {chromium} = require('playwright');
  const browser = await chromium.launch({headless:true, ...(process.env.APF_CHROMIUM_EXECUTABLE ? {executablePath:process.env.APF_CHROMIUM_EXECUTABLE} : {})});
  try {
    const context = await browser.newContext({viewport:{width,height:844},serviceWorkers:'block',javaScriptEnabled:false,offline:true});
    await context.route('**/*', route=>route.abort());
    const page = await context.newPage();
    await page.setContent(fs.readFileSync(html,'utf8')); 
    if (css) await page.addStyleTag({content:fs.readFileSync(css,'utf8')});
    await page.waitForFunction(()=>document.fonts.status==='loaded',null,{timeout:10000});
    const samples = await page.evaluate(roles=>roles.map(({role,selector})=>{
      const el=document.querySelector(selector);if(!el)throw Error('role missing: '+role);
      const s=getComputedStyle(el);
      const hex=c=>{const n=c.match(/^rgb\((\d+), (\d+), (\d+)\)$/);if(!n)throw Error('opaque RGB required: '+c);return '#'+n.slice(1).map(x=>Number(x).toString(16).padStart(2,'0')).join('');};
      let bg=el, background, complex=false;
      while(bg){const q=getComputedStyle(bg);complex ||= q.backgroundImage!=='none';if(q.backgroundColor!=='rgba(0, 0, 0, 0)'){background=hex(q.backgroundColor);break;}bg=bg.parentElement;}
      if(complex)throw Error('complex background needs manual review: '+role);
      const size=parseFloat(s.fontSize), line=s.lineHeight==='normal'?null:parseFloat(s.lineHeight)/size;
      if(line===null)throw Error('explicit line-height required for measurement: '+role);
      return {role,selector,font_size_px:size,line_height:line,font_family:s.fontFamily,
        gap_px:s.gap==='normal'?0:parseFloat(s.rowGap),foreground:hex(s.color),background:background||'#ffffff',
        overflow_px:Math.max(0,el.scrollWidth-el.clientWidth)};
    }),roles);
    const screenshot=await page.screenshot({fullPage:true,timeout:15000});
    fs.mkdirSync(path.dirname(path.resolve(output)),{recursive:true});
    fs.writeFileSync(output+'.png',screenshot);
    const observation={schema_version:'apf.design-observation/v1',source:{url:sourceUrl,usage:'PRINCIPLES_ONLY',
      observed_at:new Date().toISOString(),artifact_sha256:hash(fs.readFileSync(html)),
      capture_kind:'OFFLINE_LOCAL_ARCHIVE',original_url_unverified:true},viewport:{width,height:844},samples,
      screenshot_sha256:hash(screenshot),opportunities:[]};
    if(css)observation.applied_css_sha256=hash(fs.readFileSync(css));
    fs.writeFileSync(output,JSON.stringify(observation,null,2));
  } finally {await browser.close();}
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
