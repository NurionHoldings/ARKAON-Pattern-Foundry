const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

test('brand-studio syncs concept button selection on update', () => {
  const src = fs.readFileSync(path.join(__dirname, '../services/brand-studio.js'), 'utf8');
  assert.ok(src.includes('function syncConceptSelection'));
  assert.ok(src.includes('button.dataset.conceptId'));
  assert.ok(src.includes('syncConceptSelection();'));
  assert.ok(src.includes('if (item.brief.conceptId) showConcepts();'));
});
