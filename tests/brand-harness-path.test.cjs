const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { verifyHarnessEntry } = require('../tools/brand-browser-harness-guard.cjs');

test('verifyHarnessEntry accepts script inside candidate checkout', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'apf-harness-'));
  const tools = path.join(dir, 'tools');
  fs.mkdirSync(tools);
  const script = path.join(tools, 'test-brand-browser.cjs');
  fs.writeFileSync(script, '// harness\n');
  verifyHarnessEntry(dir, script, 'tools/test-brand-browser.cjs');
});

test('verifyHarnessEntry rejects script outside candidate checkout', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'apf-harness-'));
  const outside = path.join(os.tmpdir(), 'outside-harness.cjs');
  fs.writeFileSync(outside, '// x\n');
  assert.throws(
    () => verifyHarnessEntry(dir, outside, 'tools/test-brand-browser.cjs'),
    /must execute from candidate checkout/,
  );
});
