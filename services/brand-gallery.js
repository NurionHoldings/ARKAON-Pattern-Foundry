/* Own procedural samples; selection and editing never imply trademark clearance. */
(()=>{
'use strict';
const creative=typeof module!=='undefined'?require('./brand-concepts.js'):window.APFBrandConcepts;
const layouts=['editorial','split','centered','signature'];
function candidates(raw){return creative.allConcepts(raw).map((c,i)=>({...c,galleryLayout:layouts[i%4],logoLockup:i%3===0?'stacked':'horizontal'}));}
function toggleShortlist(ids,id,available){
 if(!available.some(c=>c.id===id))throw Error('알 수 없는 견본입니다.');
 const unique=[...new Set(ids)].filter(x=>available.some(c=>c.id===x));
 if(unique.includes(id))return unique.filter(x=>x!==id);
 if(unique.length>=4)throw Error('비교 후보는 최대 4개입니다. 하나를 빼고 담아주세요.');
 return [...unique,id];
}
function choose(raw,id,ids){
 const all=candidates(raw),valid=[...new Set(ids)].filter(x=>all.some(c=>c.id===x));
 if(valid.length<3||valid.length>4||!valid.includes(id))throw Error('후보 3~4개를 담은 뒤 그중 하나를 선택하세요.');
 const c=all.find(x=>x.id===id);
 return {...creative.applyConcept(raw,c),galleryLayout:c.galleryLayout,logoLockup:c.logoLockup,shortlistedConceptIds:JSON.stringify(valid)};
}
const api={candidates,toggleShortlist,choose};if(typeof module!=='undefined')module.exports=api;
if(typeof document==='undefined'||!document.getElementById('gallery-grid'))return;
const studio=window.APFBrandStudio,home=window.APFHomeServices;
const key='apf-brand-gallery-v1';let ids=[],selected='',projectId=null,extraBrief={};
const fields=['businessName','industry','services','tagline','brandIntro','accent'];
const status=document.getElementById('gallery-status');
const values=()=>({...extraBrief,...Object.fromEntries(fields.map(k=>[k,document.getElementById(k).value]))});
function persist(){try{localStorage.setItem(key,JSON.stringify({brief:values(),ids,selected,projectId}));return true;}catch{status.textContent='이 브라우저에 견본 선택을 저장하지 못했습니다. 입력은 유지됩니다. 저장 공간을 확인하고 다시 시도하세요.';return false;}}
function selectionState(){
 document.querySelectorAll('[data-shortlist]').forEach(b=>{const on=ids.includes(b.dataset.shortlist);b.setAttribute('aria-pressed',String(on));b.textContent=on?'비교에서 빼기':'비교에 담기';});
 document.querySelectorAll('[data-choose]').forEach(b=>{b.disabled=ids.length<3||!ids.includes(b.dataset.choose);b.setAttribute('aria-pressed',String(selected===b.dataset.choose));});
 document.getElementById('shortlist-count').textContent=`비교 후보 ${ids.length}/4 · 3~4개를 담아주세요`;
 document.getElementById('continue-editing').disabled=!selected||ids.length<3||!ids.includes(selected);
}
function render(){
 const raw=values(),all=candidates(raw),grid=document.getElementById('gallery-grid');grid.replaceChildren();
 all.forEach((c,index)=>{
  const article=document.createElement('article');article.className='sample';article.dataset.sampleId=c.id;
  const title=document.createElement('h2');title.textContent=`${String(index+1).padStart(2,'0')} · ${c.name}`;
  const brief={...creative.applyConcept(raw,c),galleryLayout:c.galleryLayout,logoLockup:c.logoLockup};
  const image=document.createElement('img');image.alt=`${c.name} 로고 견본`;image.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(studio.logo(brief));
  image.style.background=window.APFBrandEditing.presentation(brief).background;
  const frame=document.createElement('iframe');frame.title=`${c.name} 명함 앞뒷면`;frame.setAttribute('sandbox','');frame.loading='lazy';
  frame.srcdoc=studio.render(brief)+'<style>body{padding:8px;background:#eef0ed}.logo,h2,body>p{display:none}.card{min-height:110px;padding:12px;border-radius:6px;margin:6px 0}.card svg{max-height:55px}.person{font-size:14px}p{margin:4px 0}.intro,.details,p{font-size:10px;line-height:1.5}.layout-signature .front{gap:8px}</style>';
  const reason=document.createElement('p');reason.textContent=c.meaning+' · '+({editorial:'정돈된 소개',split:'측면 강조',centered:'중앙 집중',signature:'역할 분할'}[c.galleryLayout]);
  const shortlist=document.createElement('button');shortlist.type='button';shortlist.dataset.shortlist=c.id;shortlist.addEventListener('click',()=>{try{ids=toggleShortlist(ids,c.id,all);if(!ids.includes(selected))selected='';selectionState();persist();}catch(e){status.textContent=e.message;}});
  const pick=document.createElement('button');pick.type='button';pick.textContent='이 견본 선택';pick.dataset.choose=c.id;pick.addEventListener('click',()=>{selected=c.id;selectionState();status.textContent=`${c.name}을 선택했습니다. 아래 버튼으로 문구·서체·구성을 이어서 다듬으세요.`;persist();});
  article.append(title,image,frame,reason,shortlist,pick);grid.append(article);
 });selectionState();
}
try{const saved=JSON.parse(localStorage.getItem(key)||'null');if(saved){fields.forEach(k=>{if(typeof saved.brief?.[k]==='string')document.getElementById(k).value=saved.brief[k];});ids=Array.isArray(saved.ids)?saved.ids.filter(x=>candidates(values()).some(c=>c.id===x)).slice(0,4):[];selected=ids.includes(saved.selected)?saved.selected:'';projectId=typeof saved.projectId==='string'?saved.projectId:null;}}catch{status.textContent='이전 견본 기록을 읽지 못했습니다. 현재 입력으로 다시 살펴볼 수 있습니다.';}
const requestedProject=new URLSearchParams(location.search).get('project')||projectId;
if(requestedProject){const item=home.readProjects().find(p=>p.id===requestedProject&&p.type==='logo-card');if(item?.brief){projectId=item.id;extraBrief={...item.brief};fields.forEach(k=>{if(typeof item.brief[k]==='string')document.getElementById(k).value=item.brief[k];});try{ids=JSON.parse(item.brief.shortlistedConceptIds||'[]').filter(x=>candidates(values()).some(c=>c.id===x)).slice(0,4);}catch{ids=[];}selected=ids.includes(item.brief.conceptId)?item.brief.conceptId:'';document.querySelector('header a[href="/services/logo-card.html"]').href='/services/logo-card.html?project='+encodeURIComponent(projectId);}}
document.getElementById('gallery-brief').addEventListener('submit',e=>{e.preventDefault();render();persist();document.getElementById('gallery-grid').scrollIntoView({behavior:'smooth',block:'start'});});
document.getElementById('continue-editing').addEventListener('click',()=>{
 try{const brief=studio.normalize(choose(values(),selected,ids));
 const saved=home.saveProject({id:projectId||undefined,type:'logo-card',title:brief.businessName||'브랜드 초안',brief,html:studio.render(brief),logo_svg:studio.logo(brief),creation_mode:'own_procedural_gallery_v1',publish_ready:false});
 projectId=saved.id;persist();location.href='/services/logo-card.html?project='+encodeURIComponent(saved.id);
 }catch(e){status.textContent=e.message==='비교 후보는 최대 4개입니다. 하나를 빼고 담아주세요.'?e.message:'초안을 저장하지 못했습니다. 입력·선택은 유지됩니다. 저장 공간을 확인하고 다시 눌러주세요.';}
});
render();
})();
