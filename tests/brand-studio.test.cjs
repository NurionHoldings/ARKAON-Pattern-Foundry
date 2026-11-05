const { test } = require('node:test');
const assert = require('node:assert/strict');
const {
  normalize,
  logo,
  render,
  suggestCopy,
  applyCopySuggestions,
  collectGaps,
} = require('../services/brand-studio.js');

test('input cannot create executable SVG or HTML', () => {
  const b = {
    businessName: '"><script>alert(1)</script>',
    initials: '<>&',
    accent: 'red;}</style><script>x</script>',
    person: '<img onerror=x>',
  };
  for (const out of [logo(b), render(b)]) {
    assert.ok(!out.includes('<script>'));
    assert.ok(!out.includes('<img'));
  }
  assert.equal(normalize(b).accent, '#31594c');
});

test('three logo structures differ and unknown style falls back', () => {
  assert.ok(logo({ style: 'orbit' }).includes('<circle'));
  assert.ok(logo({ style: 'frame' }).includes('<rect'));
  assert.ok(!logo({ style: 'wordmark' }).includes('<circle'));
  assert.equal(normalize({ style: 'bad' }).style, 'orbit');
});

test('front and back include actual contact and identity', () => {
  const out = render({
    businessName: '햇살',
    person: '김예시',
    email: 'test@example.com',
    address: '서울',
    tagline: '태양광 상담',
    industry: '에너지',
  });
  for (const value of ['명함 앞면', '명함 뒷면', '김예시', 'test@example.com', '서울', '태양광 상담']) {
    assert.ok(out.includes(value));
  }
});

test('sample and missing information remain visible', () => {
  assert.ok(render({ sample: true }).includes('가상 예시'));
  assert.ok(render({}).includes('연락 방법 입력 필요'));
  assert.equal(normalize({ initials: '🌞🌞🌞🌞🌞' }).initials, '🌞🌞🌞🌞');
});

test('suggestCopy reflects business facts without invented claims', () => {
  const s = suggestCopy({
    businessName: '온유',
    industry: '카페',
    audience: '동네 주민',
    services: '원두 판매\n브런치',
    strengths: '직접 로스팅',
  });
  assert.ok(s.brandIntro.includes('카페'));
  assert.ok(s.brandIntro.includes('동네 주민'));
  assert.ok(s.brandIntro.includes('원두'));
  assert.ok(s.tagline.includes('로스팅'));
  assert.ok(!/인증|수상|할인|\d+%|\d+원/.test(`${s.tagline} ${s.brandIntro}`));
});

test('applyCopySuggestions fills only empty copy fields', () => {
  const base = {
    businessName: 'A',
    industry: '디자인',
    audience: '스타트업',
    services: '로고',
    strengths: '명확한 설명',
    tagline: '기존 한 줄',
    brandIntro: '',
  };
  const merged = applyCopySuggestions(base);
  assert.equal(merged.tagline, '기존 한 줄');
  assert.ok(merged.brandIntro.includes('디자인'));
});

test('personal layout puts person on front and company on back', () => {
  const out = render({
    cardLayout: 'personal',
    person: '이담당',
    businessName: '테스트 상호',
    tagline: '한 줄',
  });
  const frontIdx = out.indexOf('명함 앞면');
  const backIdx = out.indexOf('명함 뒷면');
  assert.ok(out.indexOf('이담당', frontIdx) < backIdx);
  assert.ok(out.indexOf('테스트 상호', backIdx) > backIdx);
});

test('collectGaps flags missing business and invalid email', () => {
  const gaps = collectGaps(
    normalize({ businessName: 'X', email: 'not-an-email', industry: '', services: '' }),
  );
  assert.ok(gaps.some((g) => g.includes('업종')));
  assert.ok(gaps.some((g) => g.includes('이메일')));
});

const creative = require('../services/brand-concepts.js');
test('six concepts have structurally different marks with reproducible variation',()=>{
 const brief={businessName:'햇살',industry:'태양광',services:'설계\n점검',strengths:'쉬운 설명'};
 const a=creative.concepts(brief);assert.equal(new Set(a.map(c=>c.id)).size,6);
 assert.deepEqual(a,creative.concepts(brief));
 const marks=a.map(c=>creative.svg({...creative.applyConcept(brief,c),logoLockup:'symbol',accent:'#123456'}));
 assert.equal(new Set(marks).size,6);
 assert.notDeepEqual(a,creative.concepts({...brief,conceptRound:'1'}));
 assert.notDeepEqual(a,creative.concepts({...brief,services:'다른 서비스'}));
});
test('concept selection preserves edited copy and supports all lockups',()=>{
 const raw={businessName:'긴상호'.repeat(15),tagline:'직접 다듬은 문구',brandIntro:'보존할 소개'};
 const picked=creative.applyConcept(raw,creative.concepts(raw)[0]);
 assert.equal(picked.tagline,raw.tagline);assert.equal(picked.brandIntro,raw.brandIntro);
 for(const logoLockup of ['horizontal','stacked','symbol']){
  const svg=creative.svg({...picked,logoLockup});assert.ok(svg.includes('<svg'));
  if(logoLockup==='symbol')assert.ok(!svg.includes('<text'));
 }
 assert.ok(logo({...picked,logoTone:'dark'}).includes('#ffffff'));
});
test('procedural SVG escapes names and rejects uncontrolled geometry',()=>{
 const c=creative.concepts({})[0];
 const svg=creative.svg({...creative.applyConcept({},c),businessName:'<script>x</script>',conceptRotation:'999 onclick=x',conceptWeight:'999'});
 assert.ok(!svg.includes('<script>'));assert.ok(!svg.includes('999'));
 assert.equal(creative.svg({conceptId:'unknown'}),null);
 assert.throws(()=>creative.applyConcept({}, {id:'unknown'}));
});

const editing=require('../services/brand-editing.js');
test('old drafts receive compatible controls and malicious numeric values are bounded',()=>{
 assert.deepEqual(editing.normalize({}),{elementModelVersion:1,symbolSize:80,logoGap:16,letterSpacing:0,logoAlign:'left'});
 assert.deepEqual(editing.normalize({symbolSize:Infinity,logoGap:999,letterSpacing:-5,logoAlign:'right onclick=x'}),{elementModelVersion:1,symbolSize:80,logoGap:64,letterSpacing:0,logoAlign:'left'});
});
test('ten undo and redo steps exactly restore element model and SVG digest',()=>{
 const {createHash}=require('node:crypto');const sha=x=>createHash('sha256').update(x).digest('hex');
 const initial=normalize({businessName:'시험 브랜드',conceptId:'horizon',tagline:'문구 보존',person:'김예시'});
 const h=editing.history(initial,10);let state=initial;
 for(let i=1;i<=10;i++){state=normalize({...initial,symbolSize:40+i*5,logoGap:8+i*4,letterSpacing:i/3,logoAlign:i%2?'center':'right'});h.push(state);}
 const final=state, expected=sha(logo(final));
 for(let i=0;i<10;i++)state=h.undo();assert.deepEqual(state,initial);assert.equal(h.canUndo,false);
 assert.equal(sha(logo(state)),sha(logo(initial)));
 for(let i=0;i<10;i++)state=h.redo();assert.deepEqual(state,final);assert.equal(sha(logo(state)),expected);assert.equal(h.canRedo,false);
 h.undo();h.push({...state,tagline:'새 분기'});assert.equal(h.canRedo,false);
});
test('history snapshots are immutable and bounded',()=>{
 const h=editing.history({x:0},10);for(let i=1;i<=15;i++)h.push({x:i});
 let state;for(let i=0;i<12;i++)state=h.undo();assert.equal(state.x,5);
 state.x=999;assert.equal(h.undo().x,5);
});
test('all concepts and legacy marks respond to controls without dropping 60 Korean characters',()=>{
 const name='가나다라마바사아자차카타파하'.repeat(5).slice(0,60);
 for(const concept of creative.concepts({businessName:name})){
  const b=normalize({...creative.applyConcept({businessName:name},concept),symbolSize:100,logoGap:64,letterSpacing:4,logoAlign:'right'});
  for(const mode of ['horizontal','stacked']){
   const out=logo({...b,logoLockup:mode});
   const text=[...out.matchAll(/<text[^>]*>(.*?)<\/text>/g)].map(x=>x[1]).join('');
   assert.equal(text,name);assert.ok(out.includes('data-symbol-size="100"'));
   assert.ok(out.includes('data-logo-gap="64"'));assert.ok(out.includes('text-anchor="end"'));
  }
 }
 assert.notEqual(logo({style:'orbit',symbolSize:40}),logo({style:'orbit',symbolSize:100}));
 assert.ok(logo({style:'wordmark',logoLockup:'symbol',businessName:'브랜드'}).includes('<text'));
});
test('saved brief JSON restores both copy and element controls',()=>{
 const b=normalize({businessName:'온유',tagline:'사용자 문구',symbolSize:55,logoGap:30,letterSpacing:2,logoAlign:'center',conceptId:'bridge',sample:true});
 const restored=normalize(JSON.parse(JSON.stringify(b)));
 assert.deepEqual(restored,b);assert.equal(logo(restored),logo(b));assert.ok(render(restored).includes('사용자 문구'));
});
