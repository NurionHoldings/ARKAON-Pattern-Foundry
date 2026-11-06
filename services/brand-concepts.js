/* Explainable procedural concepts. Originality/trademark clearance requires review. */
(() => {
  'use strict';
  const editing=typeof module!=='undefined'?require('./brand-editing.js'):window.APFBrandEditing;
  const esc=v=>String(v||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const families=[
    {id:'horizon',name:'지평선',meaning:'새로운 시작과 확장',shape:'<path d="M16 58H84M25 52A25 25 0 0 1 75 52M50 14V22M20 25L26 31M80 25L74 31"/>',layout:'company'},
    {id:'bridge',name:'연결의 다리',meaning:'고객과 서비스의 연결',shape:'<path d="M15 72V45Q50 5 85 45V72M15 48H85M30 35V72M50 26V72M70 35V72"/>',layout:'personal'},
    {id:'facet',name:'모듈의 결합',meaning:'여러 서비스를 하나의 체계로 구성',shape:'<path d="M50 10L88 32V72L50 94L12 72V32ZM12 32L50 54L88 32M50 54V94M50 10V54"/>',layout:'company'},
    {id:'bloom',name:'겹쳐 피는 형태',meaning:'협력과 단계적인 성장',shape:'<path d="M50 50C5 5 5 80 50 50C95 5 95 80 50 50C5 95 80 95 50 50C5 5 80 5 50 50Z"/>',layout:'personal'},
    {id:'route',name:'열린 경로',meaning:'문제에서 해결까지 이어지는 과정',shape:'<path d="M15 75H45Q70 75 70 50V25M50 25H85M75 15L85 25L75 35"/><circle cx="18" cy="75" r="7"/>',layout:'company'},
    {id:'signal',name:'중심과 파동',meaning:'핵심 가치를 중심으로 퍼지는 영향',shape:'<circle cx="50" cy="50" r="10"/><path d="M30 30A29 29 0 0 0 30 70M70 30A29 29 0 0 1 70 70M17 17A47 47 0 0 0 17 83M83 17A47 47 0 0 1 83 83"/>',layout:'personal'},
    {id:'leaf',name:'잎의 균형',meaning:'자연과 지속적인 돌봄',shape:'<path d="M18 78Q8 15 82 18Q87 87 18 78ZM18 78L68 32M42 55L36 32M42 55L67 61"/>',layout:'company'},
    {id:'compass',name:'방향의 기준',meaning:'목적과 판단의 방향',shape:'<path d="M50 8L62 38L92 50L62 62L50 92L38 62L8 50L38 38ZM38 62L62 38"/>',layout:'personal'},
    {id:'steps',name:'차곡차곡',meaning:'쌓아 가는 과정과 성취',shape:'<path d="M12 85H35V62H57V39H80V15M12 62H35M35 39H57M57 15H80"/>',layout:'company'},
    {id:'ribbon',name:'유연한 띠',meaning:'변화를 잇는 부드러운 흐름',shape:'<path d="M12 60Q28 5 50 48Q72 92 88 35M12 75Q28 20 50 63Q72 107 88 50"/>',layout:'personal'},
    {id:'window',name:'열린 창',meaning:'정돈된 공간과 새로운 관점',shape:'<rect x="14" y="14" width="72" height="72" rx="4"/><path d="M14 40H86M42 40V86M55 54H72M55 67H72"/>',layout:'company'},
    {id:'orbit-grid',name:'중심의 질서',meaning:'서로 다른 역할의 균형',shape:'<circle cx="50" cy="50" r="30"/><path d="M20 50H80M50 20V80M29 29L71 71M29 71L71 29"/><circle cx="50" cy="50" r="8"/>',layout:'personal'},
  ];
  function hash(text){let n=2166136261;for(const c of String(text)){n^=c.codePointAt(0);n=Math.imul(n,16777619);}return n>>>0;}
  function concepts(raw,{all=false}={}){
    const source=JSON.stringify([raw.businessName,raw.industry,raw.audience,raw.services,raw.strengths,raw.conceptRound||'0']);
    const seed=hash(source);
    const ordered=(all?families:families.slice(0,6)).map((f,i)=>({...f,order:hash(`${seed}:${i}`)})).sort((a,b)=>a.order-b.order);
    return ordered.map((f,i)=>({id:f.id,name:f.name,meaning:f.meaning,cardLayout:f.layout,
      rotation:[0,15,-15][hash(`${seed}:${f.id}`)%3],
      weight:3+hash(`${f.id}:${seed}`)%3,
      rationale:[raw.industry?`업종: ${String(raw.industry).slice(0,80)}`:'업종 입력 필요',raw.services?`서비스: ${String(raw.services).split('\n')[0].slice(0,80)}`:'서비스 입력 필요',`표현 의도: ${f.meaning}`].join(' / '),
      copyFocus:['strengths','services','audience'][i%3],seed:String(seed)}));
  }
  function applyConcept(raw,c){
    if(!families.some(f=>f.id===c.id))throw Error('UNKNOWN_CONCEPT');
    const next={...raw,conceptId:c.id,conceptRotation:String(c.rotation),conceptWeight:String(c.weight),cardLayout:c.cardLayout};
    if(!String(raw.tagline||'').trim()){
      const fact=String(raw[c.copyFocus]||raw.services||raw.strengths||'').split('\n')[0];
      next.tagline=fact.slice(0,100);
    }
    return next;
  }
  function svg(raw){
    const f=families.find(f=>f.id===raw.conceptId);if(!f)return null;
    const rotation=[0,15,-15].includes(Number(raw.conceptRotation))?Number(raw.conceptRotation):0;
    const weight=[3,4,5].includes(Number(raw.conceptWeight))?Number(raw.conceptWeight):4;
    const mark=`<g transform="rotate(${rotation} 50 50)" fill="none" stroke="currentColor" stroke-width="${weight}" stroke-linecap="round" stroke-linejoin="round">${f.shape}</g>`;
    return editing.compose(raw,mark,f.name);
  }
  const api={concepts,allConcepts:raw=>concepts(raw,{all:true}),applyConcept,svg};if(typeof module!=='undefined')module.exports=api;
  if(typeof window!=='undefined')window.APFBrandConcepts=api;
})();
