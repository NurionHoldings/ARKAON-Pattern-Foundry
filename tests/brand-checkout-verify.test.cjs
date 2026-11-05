const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { execSync } = require('node:child_process');
const { verifyCheckoutDir } = require('../tools/brand-browser-git-verify.cjs');

function initRepo() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'apf-git-verify-'));
  execSync('git init', { cwd: dir, stdio: 'ignore' });
  execSync('git config user.email "test@example.com"', { cwd: dir, stdio: 'ignore' });
  execSync('git config user.name "test"', { cwd: dir, stdio: 'ignore' });
  fs.writeFileSync(path.join(dir, 'f.txt'), 'x\n');
  execSync('git add f.txt', { cwd: dir, stdio: 'ignore' });
  execSync('git commit -m init', { cwd: dir, stdio: 'ignore' });
  const head = execSync('git rev-parse HEAD', { cwd: dir, encoding: 'utf8' }).trim();
  return { dir, head };
}

test('verifyCheckoutDir accepts matching clean HEAD', () => {
  const { dir, head } = initRepo();
  verifyCheckoutDir(dir, 'repo', head);
});

test('verifyCheckoutDir rejects HEAD mismatch', () => {
  const { dir } = initRepo();
  assert.throws(
    () => verifyCheckoutDir(dir, 'repo', 'a'.repeat(40)),
    /HEAD .* != expected/,
  );
});

test('verifyCheckoutDir rejects dirty working tree', () => {
  const { dir, head } = initRepo();
  fs.writeFileSync(path.join(dir, 'dirty.txt'), 'y\n');
  assert.throws(() => verifyCheckoutDir(dir, 'repo', head), /working tree not clean/);
});
