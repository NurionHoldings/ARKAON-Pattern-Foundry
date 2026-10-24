/* Browser-only concept selection regression (CI + local APF_RUN_BROWSER=1). */
const path = require('node:path');
const http = require('node:http');
const fs = require('node:fs');
const { chromium } = require('playwright');
const { verifyCheckoutDir } = require('./brand-browser-git-verify.cjs');
const { verifyHarnessEntry } = require('./brand-browser-harness-guard.cjs');
const { runConceptInteractionChecks, readConceptSelection } = require('./brand-concept-interaction.cjs');

const args = Object.fromEntries(
  process.argv.slice(2).reduce((a, v, i, s) => (i % 2 ? a : [...a, [v.replace(/^--/, ''), s[i + 1]]]), []),
);
for (const key of ['candidate-dir', 'candidate-sha']) {
  if (!args[key]) throw new Error(`Missing --${key}`);
}
if (!/^[0-9a-f]{40}$/.test(args['candidate-sha'])) throw new Error('Full candidate-sha required');

verifyCheckoutDir(args['candidate-dir'], 'candidate-dir', args['candidate-sha']);
verifyHarnessEntry(args['candidate-dir'], process.argv[1], 'tools/test-brand-concept-selection.cjs');

async function serve(dir) {
  const root = path.resolve(dir);
  const server = http.createServer((req, res) => {
    try {
      const file = path.resolve(root, '.' + decodeURIComponent(new URL(req.url, 'http://localhost').pathname));
      if (!file.startsWith(root + path.sep) || !fs.statSync(file).isFile()) {
        res.writeHead(404);
        return res.end();
      }
      const mime =
        { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css' }[path.extname(file)] ||
        'application/octet-stream';
      res.writeHead(200, { 'Content-Type': `${mime};charset=utf-8` });
      res.end(fs.readFileSync(file));
    } catch {
      res.writeHead(404);
      res.end();
    }
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  return { server, url: `http://127.0.0.1:${server.address().port}/services/logo-card.html` };
}

(async () => {
  let browser;
  let server;
  const report = {
    schema_version: 'apf.brand-concept-selection/v1',
    candidate_commit: args['candidate-sha'],
    browser_concept_interaction: 'NOT_RUN',
    browser_concept_undo_sync: 'NOT_RUN',
    status: 'FAIL',
  };
  try {
    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 390, height: 900 } });
    const served = await serve(args['candidate-dir']);
    server = served.server;
    const { url } = served;
    await page.goto(url, { waitUntil: 'load' });
    await page.getByRole('button', { name: '가상 예시로 살펴보기', exact: true }).click();
    const interaction = await runConceptInteractionChecks(page);
    report.browser_concept_interaction = interaction.status;
    report.concept_interaction_evidence = interaction.evidence;

    await page.getByRole('button', { name: '사업 정보로 디자인 방향 6개 비교', exact: true }).click();
    await page.locator('.concept').filter({ hasText: '지평선' }).click();
    await page.locator('#symbolSize').fill('55');
    await page.getByRole('button', { name: '실행 취소', exact: true }).click();
    const undoSel = await readConceptSelection(page);
    report.browser_concept_undo_sync =
      undoSel.eval.status === 'PASS' && undoSel.eval.ok ? 'PASS' : 'FAIL';
    report.concept_undo_evidence = undoSel;

    report.status =
      report.browser_concept_interaction === 'PASS' && report.browser_concept_undo_sync === 'PASS'
        ? 'PASS'
        : 'FAIL';
  } catch (error) {
    report.execution_error = String(error.stack || error);
    report.status = 'FAIL';
  } finally {
    if (browser) await browser.close();
    if (server) await new Promise((resolve) => server.close(resolve));
    console.log(JSON.stringify(report));
    if (report.status !== 'PASS') process.exitCode = 1;
  }
})();
