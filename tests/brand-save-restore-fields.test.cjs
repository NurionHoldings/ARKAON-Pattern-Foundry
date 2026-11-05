const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {
  RESTORE_FIELD_IDS,
  STUDIO_PERSISTED_FIELDS,
} = require('../tools/brand-browser-restore-fields.cjs');

test('restore snapshot covers brand-studio persisted fields', () => {
  for (const key of STUDIO_PERSISTED_FIELDS) {
    assert.ok(RESTORE_FIELD_IDS.includes(key), `missing restore field: ${key}`);
  }
});

test('save/reopen harness compares business, brand, contact, concept, and sample flag', () => {
  const required = [
    'industry',
    'audience',
    'services',
    'strengths',
    'brandIntro',
    'email',
    'phone',
    'website',
    'address',
    'conceptId',
    'conceptRound',
    'conceptRotation',
    'conceptWeight',
    'cardLayout',
    'style',
    'accent',
    'logoLockup',
    'logoTone',
  ];
  for (const key of required) {
    assert.ok(RESTORE_FIELD_IDS.includes(key), `missing: ${key}`);
  }
  const source = fs.readFileSync(path.join(__dirname, '../tools/test-brand-browser.cjs'), 'utf8');
  assert.ok(source.includes('out.sample'));
  assert.ok(source.includes('concept_selection_status'));
  assert.ok(source.includes('readConceptSelection'));
});
