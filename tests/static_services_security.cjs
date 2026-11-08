const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const storage = new Map();
const context = {window:{},URL,localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)}};
vm.runInNewContext(fs.readFileSync('services/services.js','utf8'),context);
const api = context.window.APFHomeServices;
for (const bad of ['{}','null','[null,3,"x"]','broken']) {
  storage.set('apf.home.projects.v1',bad);
  assert.equal(api.readProjects().length,0);
}
for (const url of ['javascript:alert(1)','data:text/html,test','file:///etc/passwd','https://user:pass@example.com']) {
  const html=api.personalPageHtml({linksText:`unsafe|${url}`});
  assert.ok(!html.includes('>unsafe</a>'));
}
assert.ok(api.personalPageHtml({linksText:'safe|https://example.com'}).includes('href="https://example.com/"'));
assert.ok(!api.siteHtml({title:'<img src=x onerror=alert(1)>'}).includes('<img'));
for (const url of ['javascript:alert(1)','https://user:pass@example.com','https://example.com?token=x','http://remote.example']) {
  assert.throws(()=>api.setApiBase(url),/API_URL_INVALID/);
}
api.setApiBase('https://api.example.com/');
assert.equal(api.getApiBase(),'https://api.example.com');
api.setApiBase('http://localhost:8443');
assert.equal(api.getApiBase(),'http://localhost:8443');
assert.throws(()=>api.downloadDataUrl('a.html','javascript:alert(1)'),/VIDEO_URL_INVALID/);
console.log('PASS: storage shape, HTML escaping, unsafe links, API origins, download URL');
