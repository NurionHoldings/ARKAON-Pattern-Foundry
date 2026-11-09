const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const storage=new Map();const c={window:{},URL,localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},crypto:{randomUUID:()=> 'test-site'}};
vm.runInNewContext(fs.readFileSync('services/services.js','utf8'),c);
vm.runInNewContext(fs.readFileSync('services/customer-design.js','utf8'),c);
const composer=c.window.APFDesignComposer;
for(const style of ['atelier','midnight','editorial'])for(const layout of ['split','stack'])for(const motion of ['luxury','subtle','none']){
 const html=composer.compose({title:'<script>alert(1)</script>',body:'<img src=x onerror=1>',style,layout,motion});
 assert.ok(!html.includes('<script>'));assert.ok(!html.includes('<img'));assert.ok(html.includes('&lt;script&gt;'));
 assert.ok(html.includes(composer.presets[style].background));assert.ok(html.includes('@media(max-width:600px)'));
 assert.ok(html.includes('prefers-reduced-motion:reduce'));
 if(motion==='none')assert.ok(html.includes('main{animation:none}'));
}
const bad=composer.normalize({style:'<style>',layout:'oops',motion:'x',accent:'red;background:url(https://bad.test)'});
assert.equal(bad.style,'atelier');assert.equal(bad.accent,'');
const elements=new Map();const el=id=>{if(!elements.has(id))elements.set(id,{value:'',textContent:'',handlers:{},addEventListener(t,f){this.handlers[t]=f;},focus(){this.focused=true;}});return elements.get(id);};
const sample={title:'우리 가게',body:'원래 소개',style:'atelier',layout:'split',motion:'luxury',accent:'#194e4a'};
Object.entries(sample).forEach(([k,v])=>el(k).value=v);
c.document={getElementById:el};c.APFHomeServices=c.window.APFHomeServices;c.APFDesignComposer=composer;c.confirm=()=>true;
let downloads=[];c.APFHomeServices.downloadText=(name,html)=>downloads.push({name,html});
vm.runInNewContext(fs.readFileSync('services/site-builder.js','utf8'),c);
const submit=()=>el('form').handlers.submit({preventDefault(){}});
assert.equal(el('preview').srcdoc,composer.compose(sample));submit();
const saved=c.APFHomeServices.readProjects()[0];assert.equal(saved.html,downloads[0].html);assert.equal(saved.html,el('preview').srcdoc);
el('title').value='다른 이름';el('loadDesign').handlers.click();assert.equal(el('title').value,'우리 가게');assert.equal(el('preview').srcdoc,saved.html);
el('style').value='midnight';el('style').handlers.input();assert.equal(el('body').value,'원래 소개');assert.equal(el('accent').value,'#b7dcd4');
el('title').value=' \t ';submit();assert.equal(downloads.length,1);
el('title').value='저장 실패';c.localStorage.setItem=()=>{throw Error('quota');};submit();assert.equal(downloads.length,1);assert.equal(el('title').value,'저장 실패');
console.log('PASS: 18 design combinations, escaping, defaults, preview/save parity, reload, content preservation, empty title and quota failure');

for(const background of ['#000000','#ffffff']){const html=composer.compose({background,buttonColor:background});assert.ok(html.includes('background-color:'+background));assert.ok(html.includes('color:'+(background==='#000000'?'#ffffff':'#000000')+';background:'+background));}
assert.ok(!composer.compose({background:'red;bad()',buttonColor:'url(https://bad.test)'}).includes('bad.test'));
