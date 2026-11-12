const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('services/mailbox.js', 'utf8');
function setup(base = 'https://example.test') {
  const nodes = new Map();
  const node = () => ({value:'',disabled:false,textContent:'',children:[],handlers:{},
    addEventListener(type,fn){this.handlers[type]=fn;},
    replaceChildren(){this.children=[];}, append(...items){this.children.push(...items);},
    focus(){this.focused=true;},select(){this.selected=true;}});
  const get = id => {if(!nodes.has(id)) nodes.set(id,node());return nodes.get(id);};
  let response, copied;
  const context = {document:{getElementById:get,createElement:node},
    APFHomeServices:{getApiBase:()=>base},AbortSignal:{timeout:()=>null},Date,
    navigator:{clipboard:{writeText:async text=>{copied=text;}}},
    fetch:async()=>response};
  vm.runInNewContext(source,context);
  return {get,context,copied:()=>copied,
    response(value,status=200){response={status,ok:status===200,headers:{get:()=> 'application/json'},json:async()=>value};},
    refresh:()=>get('refreshMailbox').handlers.click(),copy:()=>get('copyMailboxReport').handlers.click()};
}
(async()=>{
  const app=setup();
  app.response([{status:'PENDING',summary:'<script>steal()</script>',private_token:'SECRET'}, {status:'COMPLETED',summary:'done'}]);
  await app.refresh();
  assert.match(app.get('mailboxReport').value,/조회 2건 · 검토 대상 1건 · 보고서 1건/);
  assert.ok(!app.get('mailboxReport').value.includes('SECRET'));
  assert.equal(app.get('mailboxItems').children[0].children[0].textContent,'<script>steal()</script>');
  await app.copy();assert.equal(app.copied(),app.get('mailboxReport').value);
  app.context.navigator.clipboard.writeText=async()=>{throw Error('denied');};
  await app.copy();assert.ok(app.get('mailboxReport').selected);
  app.response(Array.from({length:35},()=>({status:'PENDING',summary:'x'.repeat(3000)})));
  await app.refresh();assert.match(app.get('mailboxReport').value,/보고서 30건/);
  assert.equal(app.get('mailboxItems').children.length,30);
  assert.ok(app.get('mailboxReport').value.length<65000);
  app.response(null,401);await app.refresh();
  assert.equal(app.get('mailboxReport').value,'');assert.equal(app.get('copyMailboxReport').disabled,true);
  app.response([]);await app.refresh();assert.match(app.get('mailboxReport').value,/조회 0건/);
  const local=setup('');local.response({items:[{summary:'운영 제안',status:'PENDING_REVIEW',details:'검토 내용'}],truncated:false});await local.refresh();
  assert.match(local.get('mailboxReport').value,/조회 1건/);assert.equal(local.get('mailboxItems').children[0].children[2].textContent,'검토 내용');
  local.response(null,503);await local.refresh();assert.equal(local.get('mailboxReport').value,'');assert.match(local.get('mailboxStatus').textContent,/아직 확인되지/);
  console.log('Mailbox report: successful/empty/truncated/error/disconnected responses, text-only rendering, clipboard fallback PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
