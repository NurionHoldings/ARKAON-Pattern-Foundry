const { test } = require('node:test');
const assert = require('node:assert/strict');
const {
  evaluateConceptSelection,
  evaluateAbUndoRedoTransition,
} = require('../tools/brand-concept-selection-eval.cjs');

test('empty conceptId with no pressed buttons is PASS', () => {
  const r = evaluateConceptSelection({ activeId: '', pressedIds: [], panelVisible: true });
  assert.equal(r.status, 'PASS');
  assert.equal(r.ok, true);
});

test('empty conceptId with a pressed button is FAIL', () => {
  const r = evaluateConceptSelection({ activeId: '', pressedIds: ['horizon'], panelVisible: true });
  assert.equal(r.status, 'FAIL');
  assert.equal(r.ok, false);
});

test('missing concept panel is NOT_RUN not auto-pass', () => {
  const r = evaluateConceptSelection({ activeId: 'horizon', pressedIds: [], panelVisible: false });
  assert.equal(r.status, 'NOT_RUN');
  assert.equal(r.ok, null);
});

test('single matching pressed id is PASS', () => {
  const r = evaluateConceptSelection({ activeId: 'horizon', pressedIds: ['horizon'], panelVisible: true });
  assert.equal(r.status, 'PASS');
  assert.equal(r.ok, true);
});

test('A→B→undo→redo transition PASS when values restore A then B', () => {
  const panel = (activeId) => ({
    activeId,
    pressedIds: activeId ? [activeId] : [],
    panelVisible: true,
  });
  const r = evaluateAbUndoRedoTransition({
    aRaw: panel('horizon'),
    bRaw: panel('bridge'),
    afterUndoRaw: panel('horizon'),
    afterRedoRaw: panel('bridge'),
  });
  assert.equal(r.status, 'PASS');
  assert.equal(r.ok, true);
  assert.equal(r.ab_distinct, true);
});

test('noop undo control FAILs even when each step aria sync looks valid', () => {
  const panel = (activeId) => ({
    activeId,
    pressedIds: activeId ? [activeId] : [],
    panelVisible: true,
  });
  const r = evaluateAbUndoRedoTransition({
    aRaw: panel('horizon'),
    bRaw: panel('bridge'),
    afterUndoRaw: panel('bridge'),
    afterRedoRaw: panel('bridge'),
  });
  assert.equal(r.status, 'FAIL');
  assert.equal(r.ok, false);
  assert.equal(r.undo_matches_a, false);
  assert.match(r.reason, /undo did not restore A/);
});

test('A and B identical fails transition', () => {
  const panel = (activeId) => ({
    activeId,
    pressedIds: [activeId],
    panelVisible: true,
  });
  const r = evaluateAbUndoRedoTransition({
    aRaw: panel('horizon'),
    bRaw: panel('horizon'),
    afterUndoRaw: panel('horizon'),
    afterRedoRaw: panel('horizon'),
  });
  assert.equal(r.ok, false);
  assert.match(r.reason, /must differ/);
});

test('redo must restore B not A', () => {
  const panel = (activeId) => ({
    activeId,
    pressedIds: [activeId],
    panelVisible: true,
  });
  const r = evaluateAbUndoRedoTransition({
    aRaw: panel('horizon'),
    bRaw: panel('bridge'),
    afterUndoRaw: panel('horizon'),
    afterRedoRaw: panel('horizon'),
  });
  assert.equal(r.ok, false);
  assert.equal(r.redo_matches_b, false);
});
