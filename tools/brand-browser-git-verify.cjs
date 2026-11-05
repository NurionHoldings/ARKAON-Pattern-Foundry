/* Git checkout guard for brand measurement/browser harnesses. */
const fs = require('node:fs');
const path = require('node:path');
const { execSync } = require('node:child_process');

function verifyCheckoutDir(dir, label, expectedSha) {
  const root = path.resolve(dir);
  if (!fs.existsSync(path.join(root, '.git'))) {
    throw new Error(`${label}: not a git checkout (${root})`);
  }
  const head = execSync('git rev-parse HEAD', { cwd: root, encoding: 'utf8' }).trim().toLowerCase();
  const want = String(expectedSha).toLowerCase();
  if (head !== want) {
    throw new Error(`${label}: HEAD ${head} != expected ${want}`);
  }
  const dirty = execSync('git status --porcelain', { cwd: root, encoding: 'utf8' }).trim();
  if (dirty) {
    throw new Error(`${label}: working tree not clean:\n${dirty}`);
  }
}

module.exports = { verifyCheckoutDir };
