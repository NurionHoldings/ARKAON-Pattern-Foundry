/* Concept panel selection rules shared by harness and unit tests. */

/**
 * @param {{ activeId: string, pressedIds: string[], panelVisible: boolean }} input
 * @returns {{ status: 'NOT_RUN'|'PASS'|'FAIL', ok: boolean|null, reason?: string }}
 */
function evaluateConceptSelection({ activeId, pressedIds, panelVisible }) {
  if (!panelVisible) {
    return { status: 'NOT_RUN', ok: null, reason: 'concept panel not rendered' };
  }
  const active = String(activeId ?? '').trim();
  const pressed = [...pressedIds];
  if (!active) {
    const ok = pressed.length === 0;
    return {
      status: ok ? 'PASS' : 'FAIL',
      ok,
      reason: ok ? 'empty conceptId with no pressed buttons' : 'empty conceptId but buttons pressed',
    };
  }
  const ok = pressed.length === 1 && pressed[0] === active;
  return {
    status: ok ? 'PASS' : 'FAIL',
    ok,
    reason: ok ? 'single pressed matches conceptId' : 'pressed set does not match conceptId',
  };
}

/** @param {{ activeId: string, pressedIds: string[], panelVisible: boolean }} raw */
function conceptSelectionSnapshot(raw) {
  const activeId = String(raw?.activeId ?? '').trim();
  const pressedIds = [...(raw?.pressedIds ?? [])].map((id) => String(id).trim()).filter(Boolean).sort();
  return { activeId, pressedIds, panelVisible: Boolean(raw?.panelVisible) };
}

function selectionSnapshotsEqual(left, right) {
  const a = conceptSelectionSnapshot(left);
  const b = conceptSelectionSnapshot(right);
  return (
    a.panelVisible &&
    b.panelVisible &&
    a.activeId === b.activeId &&
    a.pressedIds.length === b.pressedIds.length &&
    a.pressedIds.every((id, i) => id === b.pressedIds[i])
  );
}

/**
 * A→B→undo→redo must restore prior selection values, not merely pass per-step aria sync.
 * @param {{ aRaw: object, bRaw: object, afterUndoRaw: object, afterRedoRaw: object }} input
 */
function evaluateAbUndoRedoTransition({ aRaw, bRaw, afterUndoRaw, afterRedoRaw }) {
  const a = conceptSelectionSnapshot(aRaw);
  const b = conceptSelectionSnapshot(bRaw);
  const reasons = [];

  if (!a.activeId) reasons.push('A conceptId empty');
  if (!b.activeId) reasons.push('B conceptId empty');
  if (a.activeId && b.activeId && a.activeId === b.activeId) {
    reasons.push('A and B must differ');
  }

  const abDistinct = Boolean(a.activeId && b.activeId && a.activeId !== b.activeId);
  const undoMatchesA = abDistinct && selectionSnapshotsEqual(aRaw, afterUndoRaw);
  const redoMatchesB = abDistinct && selectionSnapshotsEqual(bRaw, afterRedoRaw);

  if (abDistinct && !undoMatchesA) reasons.push('undo did not restore A');
  if (abDistinct && !redoMatchesB) reasons.push('redo did not restore B');

  const ok = abDistinct && undoMatchesA && redoMatchesB;
  return {
    status: ok ? 'PASS' : 'FAIL',
    ok,
    ab_distinct: abDistinct,
    undo_matches_a: undoMatchesA,
    redo_matches_b: redoMatchesB,
    a_concept_id: a.activeId,
    b_concept_id: b.activeId,
    reason: ok ? 'A→B→undo→redo restored selection values' : reasons.join('; ') || 'transition check failed',
  };
}

function browserEvaluateSnippet() {
  return `(() => {
    const root = document.getElementById('concept-options');
    const panelVisible = Boolean(root?.querySelector('.concept'));
    const activeId = document.getElementById('conceptId')?.value ?? '';
    const pressedIds = panelVisible
      ? [...root.querySelectorAll('.concept[aria-pressed="true"]')].map((b) => b.dataset.conceptId)
      : [];
    return { activeId, pressedIds, panelVisible };
  })()`;
}

module.exports = {
  evaluateConceptSelection,
  evaluateAbUndoRedoTransition,
  selectionSnapshotsEqual,
  conceptSelectionSnapshot,
  browserEvaluateSnippet,
};
