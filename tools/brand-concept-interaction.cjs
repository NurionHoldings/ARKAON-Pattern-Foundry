/* Playwright concept switch / default draft / selection checks (candidate UI). */
const { evaluateConceptSelection, evaluateAbUndoRedoTransition } = require('./brand-concept-selection-eval.cjs');

async function readConceptSelection(page) {
  const raw = await page.evaluate(() => {
    const root = document.getElementById('concept-options');
    const panelVisible = Boolean(root?.querySelector('.concept'));
    const activeId = document.getElementById('conceptId')?.value ?? '';
    const pressedIds = panelVisible
      ? [...root.querySelectorAll('.concept[aria-pressed="true"]')].map((b) => b.dataset.conceptId)
      : [];
    return { activeId, pressedIds, panelVisible };
  });
  return { raw, eval: evaluateConceptSelection(raw) };
}

async function ensureConceptPanel(page) {
  const has = await page.locator('#concept-options .concept').count();
  if (has > 0) return;
  await page.getByRole('button', { name: '사업 정보로 디자인 방향 6개 비교', exact: true }).click();
}

async function runConceptInteractionChecks(page) {
  const evidence = {};
  await ensureConceptPanel(page);
  await page.locator('.concept').nth(0).click();
  const a = await readConceptSelection(page);
  evidence.concept_a = a;
  await page.locator('.concept').nth(1).click();
  const b = await readConceptSelection(page);
  evidence.concept_b = b;
  await page.getByRole('button', { name: '실행 취소', exact: true }).click();
  const afterUndo = await readConceptSelection(page);
  evidence.after_ab_undo = afterUndo;
  await page.getByRole('button', { name: '다시 실행', exact: true }).click();
  const afterRedo = await readConceptSelection(page);
  evidence.after_ab_redo = afterRedo;

  await page.locator('#style').selectOption('frame');
  const afterStyle = await readConceptSelection(page);
  evidence.after_default_style = afterStyle;

  const transition = evaluateAbUndoRedoTransition({
    aRaw: a.raw,
    bRaw: b.raw,
    afterUndoRaw: afterUndo.raw,
    afterRedoRaw: afterRedo.raw,
  });
  evidence.ab_undo_redo_transition = transition;

  const displayOk = a.eval.ok && b.eval.ok && afterUndo.eval.ok && afterRedo.eval.ok;
  const abUndoPass = displayOk && transition.ok;
  const defaultPass = afterStyle.eval.ok && !afterStyle.raw.activeId;
  const status = abUndoPass && defaultPass ? 'PASS' : 'FAIL';
  return {
    status,
    evidence,
    ab_switch_undo_redo: abUndoPass ? 'PASS' : 'FAIL',
    ab_undo_redo_transition: transition.status,
    default_draft_empty_selection: defaultPass ? 'PASS' : 'FAIL',
  };
}

module.exports = { readConceptSelection, ensureConceptPanel, runConceptInteractionChecks };
