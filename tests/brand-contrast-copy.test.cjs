const {test}=require('node:test');
const assert=require('node:assert/strict');
const editing=require('../services/brand-editing.js');
const studio=require('../services/brand-studio.js');
for(const accent of ['#ffffff','#fffffe','#e3c46d','#888888','#31594c','#000000']){
 for(const logoTone of ['light','dark','mono']) test(`readable surface preserves logo color ${accent}/${logoTone}`,()=>{
  const raw={accent,logoTone};const p=editing.presentation(raw);
  assert.ok(p.contrast>=4.5);
  assert.equal(p.foreground,logoTone==='dark'?'#ffffff':logoTone==='mono'?'#172b24':accent);
  assert.equal(raw.accent,accent);
 });
}
test('white brand survives company card and preview on a contrasting surface',()=>{
 const raw={businessName:'햇살 에너지',accent:'#ffffff',logoTone:'light',conceptId:'horizon'};
 const html=studio.render(raw);
 assert.match(html,/class="card-logo" style="background:#172b24"/);
 assert.match(html,/\.logo\{background:#172b24/);
 assert.match(html,/브랜드색은 그대로입니다/);
 assert.match(studio.logo(raw),/fill="#ffffff"/);
 assert.equal(studio.normalize(raw).accent,'#ffffff');
});
for(const name of ['햇살 에너지','온유','누리온','ARKAON','서울 24']) test(`natural fact-bound copy for ${name}`,()=>{
 const copy=studio.suggestCopy({businessName:name,industry:'브랜드 디자인',audience:'소상공인'});
 assert.equal(copy.brandIntro,`브랜드 디자인 분야의 ${name}입니다. 주요 고객은 소상공인입니다.`);
 assert.equal(copy.tagline,'소상공인 대상 브랜드 디자인');
 assert.doesNotMatch(JSON.stringify(copy),/은\(는\)|을\(를\)|인증|수상|최고|할인|\d+원/);
});
test('no invented facts and no replacement of user-edited copy',()=>{
 assert.deepEqual(studio.suggestCopy({}),{tagline:'',brandIntro:''});
 const raw={businessName:'A',industry:'카페',tagline:'직접 작성',brandIntro:'직접 쓴 소개'};
 assert.deepEqual(studio.applyCopySuggestions(raw),raw);
});
