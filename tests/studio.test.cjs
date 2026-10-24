const {test}=require('node:test');
const assert=require('node:assert/strict');
const {compose,render}=require('../services/studio.js');

test('industry changes the actual content architecture',()=>{
  const service=render({industry:'service'}),shop=render({industry:'shop'}),portfolio=render({industry:'portfolio'});
  assert.match(service,/어떤 도움을 드리나요/);assert.match(shop,/가격과 이용시간/);
  assert.match(portfolio,/소개하고 싶은 작업/);assert.match(portfolio,/맡은 역할/);
});
test('user details replace writing guides and survive rendering',()=>{
  const raw={title:'우리 가게',offerings:'방향 상담 | 고객과 메시지를 정리합니다.'};
  assert.equal(compose(raw).offerings[0].detail,'고객과 메시지를 정리합니다.');
  assert.ok(!compose(raw).needs.includes('대표 항목 1 상세 설명'));
  assert.match(render(raw),/고객과 메시지를 정리합니다./);
});
test('untrusted text cannot escape into active markup',()=>{
  const html=render({title:'<script>alert(1)</script>',story:'<img src=x onerror=alert(1)>',offerings:'<svg onload=x> | <iframe src=x>'});
  assert.ok(!html.includes('<script>'));assert.ok(!html.includes('<img '));assert.ok(!html.includes('<iframe '));
  assert.match(html,/&lt;script&gt;/);
});
test('invalid style tokens fall back and all themes are distinct',()=>{
  assert.equal(compose({theme:'" onload=x'}).theme,'editorial');
  for(const theme of ['editorial','night','minimal'])assert.match(render({theme}),new RegExp(`body class="${theme}"`));
  assert.match(render({}),/\.night \.hero\{grid-template-columns:1fr/);
  assert.match(render({}),/\.minimal \.visual\{display:none/);
});
test('empty content and examples cannot silently look publish-ready',()=>{
  assert.ok(compose({}).needs.includes('연락 안내'));assert.ok(compose({}).needs.includes('대표 항목 1 상세 설명'));
  assert.match(render({sample:true}),/가상 예시 · 실제 사업 정보가 아닙니다/);
  assert.match(render({}),/상담·예약 접수 기능은 연결되지 않았습니다/);
  assert.ok(!render({}).includes('<form'));assert.ok(!render({}).includes('mailto:'));
});
test('bounded content and internal navigation work for every industry',()=>{
  const raw={offerings:Array.from({length:30},(_,i)=>`항목${i} | 설명`).join('\n')};
  assert.equal(compose(raw).offerings.length,8);
  const html=render(raw);
  for(const id of ['offer','about','contact']){assert.ok(html.includes(`href="#${id}"`));assert.ok(html.includes(`id="${id}"`));}
  assert.match(html,/@media\(max-width:650px\)/);
});
