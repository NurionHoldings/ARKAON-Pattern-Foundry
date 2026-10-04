const fs=require('fs'),assert=require('assert');
const {JSDOM,VirtualConsole}=require('jsdom');
const errors=[];const vc=new VirtualConsole();vc.on('jsdomError',e=>{if(!e.message.includes('Could not parse CSS'))errors.push(e.message);});
const gallery=new JSDOM(fs.readFileSync('examples/entry-effects-studio.html','utf8'),{runScripts:'dangerously',virtualConsole:vc});
const w=gallery.window,d=w.document;
assert.equal(d.querySelectorAll('#effect option').length,9);
for(const option of d.querySelectorAll('#effect option')){
 d.getElementById('effect').value=option.value;d.getElementById('title').value='<script>alert(1)</script> 테스트';d.getElementById('play').click();
 const page=d.getElementById('preview').srcdoc;
 assert(page.includes(`data-effect="${option.value}"`));
 const dom=new JSDOM(page,{runScripts:'dangerously',virtualConsole:vc,beforeParse(win){win.matchMedia=()=>({matches:true});}});
 assert.equal(dom.window.document.querySelector('h1').textContent,'<script>alert(1)</script> 테스트');
 let entered=0;dom.window.document.addEventListener('arkaon:entered',e=>{entered++;assert.equal(e.detail.effect,option.value);});
 dom.window.document.querySelector('.apf-enter').click();assert.equal(entered,1);assert.equal(dom.window.document.querySelector('main').hidden,false);
 dom.window.document.querySelector('[data-replay]').click();assert.equal(dom.window.document.querySelector('.apf-gate').hidden,false);
 dom.window.document.querySelector('.apf-skip').click();assert.equal(entered,2);
 dom.window.close();
}
assert.deepEqual(errors,[]);gallery.window.close();console.log('DOM checks PASS: 9 selections, editable safe text, selected effect events, enter/skip/replay and reduced-motion flow');
