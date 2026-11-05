const {test}=require('node:test'),assert=require('node:assert/strict');
const {compose,render,foundationPresets}=require('../services/studio.js');
const foundations=require('../services/platform-presets.js');
for(const id of ['dapanda','arirang'])test(`${id} foundation is selectable and content survives`,()=>{
 const raw={theme:id,title:'햇살 에너지',industry:'service',story:'사용자가 작성한 소개',offerings:'현장 상담 | 조건 확인',contact:'직접 작성한 연락 안내'};
 assert.equal(compose(raw).theme,id);
 const saved=JSON.parse(JSON.stringify(raw));assert.equal(render(saved),render(raw));
 assert.match(render(raw),new RegExp(`body class="${id}"`));
 for(const text of [raw.title,raw.story,raw.contact,'조건 확인'])assert.ok(render(raw).includes(text));
 assert.ok(!render(raw).includes('다판다.store'));assert.ok(!render(raw).includes('더아리랑.com'));
 assert.ok(!render(raw).includes('<script'));assert.ok(!render(raw).includes('<img'));
});
test('measured color tokens and responsive layouts are active',()=>{
 assert.equal(foundationPresets.length,2);
 assert.match(foundations.styles('dapanda'),/--bg:#0b0b0a/);
 assert.match(foundations.styles('dapanda'),/--accent:#e3c46d/);
 assert.match(foundations.styles('arirang'),/--bg:#f3f6fc/);
 assert.match(foundations.styles('arirang'),/linear-gradient\(115deg,#163b70,#285998\)/);
 for(const id of ['dapanda','arirang'])assert.match(foundations.styles(id),/@media\(max-width:650px\)/);
});
test('old themes and invalid token fallback remain compatible',()=>{
 for(const theme of ['editorial','night','minimal'])assert.equal(compose({theme}).theme,theme);
 assert.equal(compose({theme:'__proto__'}).theme,'editorial');
 assert.equal(compose({theme:'arirang" onload=x'}).theme,'editorial');
 assert.equal(foundations.styles('__proto__'),'');
 assert.doesNotMatch(render({theme:'dapanda',title:'<script>x</script>'}),/<script>/);
});
