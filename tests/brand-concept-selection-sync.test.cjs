const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');

const runBrowser = process.env.APF_RUN_BROWSER === '1';

test(
  'concept aria-pressed stays aligned after undo/redo (browser)',
  { skip: runBrowser ? false : 'set APF_RUN_BROWSER=1 and Playwright chromium' },
  async (t) => {
    const { chromium } = require('playwright');
    const root = path.resolve(__dirname, '..');

    async function serve() {
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

    const { server, url } = await serve();
    t.after(() => new Promise((resolve) => server.close(resolve)));
    const browser = await chromium.launch({ headless: true });
    t.after(() => browser.close());
    const page = await browser.newPage({ viewport: { width: 390, height: 900 } });
    await page.goto(url, { waitUntil: 'load' });
    await page.getByRole('button', { name: '가상 예시로 살펴보기', exact: true }).click();
    await page.getByRole('button', { name: '사업 정보로 디자인 방향 6개 비교', exact: true }).click();
    await page.locator('.concept').filter({ hasText: '지평선' }).click();
    await page.locator('#symbolSize').fill('55');
    await page.getByRole('button', { name: '실행 취소', exact: true }).click();
    const afterUndo = await page.evaluate(() => {
      const active = document.getElementById('conceptId')?.value ?? '';
      const pressed = [...document.querySelectorAll('#concept-options .concept[aria-pressed="true"]')];
      return {
        active,
        pressedId: pressed.length === 1 ? pressed[0].dataset.conceptId : null,
      };
    });
    assert.equal(afterUndo.pressedId, afterUndo.active);
    assert.ok(afterUndo.active);
    await page.getByRole('button', { name: '다시 실행', exact: true }).click();
    const afterRedo = await page.evaluate(() => {
      const active = document.getElementById('conceptId')?.value ?? '';
      const pressed = [...document.querySelectorAll('#concept-options .concept[aria-pressed="true"]')];
      return pressed.length === 1 && pressed[0].dataset.conceptId === active;
    });
    assert.equal(afterRedo, true);
  },
);
