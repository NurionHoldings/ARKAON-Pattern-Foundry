const { test } = require('node:test');
const assert = require('node:assert/strict');
const {
  normalize,
  logo,
  render,
  suggestCopy,
  applyCopySuggestions,
  collectGaps,
} = require('../services/brand-studio.js');

test('input cannot create executable SVG or HTML', () => {
  const b = {
    businessName: '"><script>alert(1)</script>',
    initials: '<>&',
    accent: 'red;}</style><script>x</script>',
    person: '<img onerror=x>',
  };
  for (const out of [logo(b), render(b)]) {
    assert.ok(!out.includes('<script>'));
    assert.ok(!out.includes('<img'));
  }
  assert.equal(normalize(b).accent, '#31594c');
});

test('three logo structures differ and unknown style falls back', () => {
  assert.ok(logo({ style: 'orbit' }).includes('<circle'));
  assert.ok(logo({ style: 'frame' }).includes('<rect'));
  assert.ok(!logo({ style: 'wordmark' }).includes('<circle'));
  assert.equal(normalize({ style: 'bad' }).style, 'orbit');
});

test('front and back include actual contact and identity', () => {
  const out = render({
    businessName: '햇살',
    person: '김예시',
    email: 'test@example.com',
    address: '서울',
    tagline: '태양광 상담',
    industry: '에너지',
  });
  for (const value of ['명함 앞면', '명함 뒷면', '김예시', 'test@example.com', '서울', '태양광 상담']) {
    assert.ok(out.includes(value));
  }
});

test('sample and missing information remain visible', () => {
  assert.ok(render({ sample: true }).includes('가상 예시'));
  assert.ok(render({}).includes('연락 방법 입력 필요'));
  assert.equal(normalize({ initials: '🌞🌞🌞🌞🌞' }).initials, '🌞🌞🌞🌞');
});

test('suggestCopy reflects business facts without invented claims', () => {
  const s = suggestCopy({
    businessName: '온유',
    industry: '카페',
    audience: '동네 주민',
    services: '원두 판매\n브런치',
    strengths: '직접 로스팅',
  });
  assert.ok(s.brandIntro.includes('카페'));
  assert.ok(s.brandIntro.includes('동네 주민'));
  assert.ok(s.brandIntro.includes('원두'));
  assert.ok(s.tagline.includes('로스팅'));
  assert.ok(!/인증|수상|할인|\d+%|\d+원/.test(`${s.tagline} ${s.brandIntro}`));
});

test('applyCopySuggestions fills only empty copy fields', () => {
  const base = {
    businessName: 'A',
    industry: '디자인',
    audience: '스타트업',
    services: '로고',
    strengths: '명확한 설명',
    tagline: '기존 한 줄',
    brandIntro: '',
  };
  const merged = applyCopySuggestions(base);
  assert.equal(merged.tagline, '기존 한 줄');
  assert.ok(merged.brandIntro.includes('디자인'));
});

test('personal layout puts person on front and company on back', () => {
  const out = render({
    cardLayout: 'personal',
    person: '이담당',
    businessName: '테스트 상호',
    tagline: '한 줄',
  });
  const frontIdx = out.indexOf('명함 앞면');
  const backIdx = out.indexOf('명함 뒷면');
  assert.ok(out.indexOf('이담당', frontIdx) < backIdx);
  assert.ok(out.indexOf('테스트 상호', backIdx) > backIdx);
});

test('collectGaps flags missing business and invalid email', () => {
  const gaps = collectGaps(
    normalize({ businessName: 'X', email: 'not-an-email', industry: '', services: '' }),
  );
  assert.ok(gaps.some((g) => g.includes('업종')));
  assert.ok(gaps.some((g) => g.includes('이메일')));
});
