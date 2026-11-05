const path = require('node:path');
const { verifyCheckoutDir } = require('./brand-browser-git-verify.cjs');

function verifyHarnessEntry(candidateDir, entryScript, relativePath) {
  const root = path.resolve(candidateDir);
  const expected = path.resolve(root, relativePath);
  const actual = path.resolve(entryScript || '');
  if (path.normalize(actual) !== path.normalize(expected)) {
    throw new Error(
      `Harness must execute from candidate checkout file ${expected}, not ${actual || '(unknown)'}`,
    );
  }
}

function guardBrandBrowserHarness(args, entryScript) {
  verifyCheckoutDir(args['baseline-dir'], 'baseline-dir', args['baseline-sha']);
  verifyCheckoutDir(args['candidate-dir'], 'candidate-dir', args['candidate-sha']);
  verifyHarnessEntry(args['candidate-dir'], entryScript, 'tools/test-brand-browser.cjs');
}

function guardMeasureHarness(args, entryScript) {
  verifyCheckoutDir(args['baseline-dir'], 'baseline-dir', args['baseline-sha']);
  verifyCheckoutDir(args['candidate-dir'], 'candidate-dir', args['candidate-sha']);
  verifyHarnessEntry(args['candidate-dir'], entryScript, 'tools/measure-brand-elements.cjs');
}

module.exports = { verifyHarnessEntry, guardBrandBrowserHarness, guardMeasureHarness };
