/* Rule-based vector drafts; no AI image generation or trademark clearance. */
(() => {
'use strict';
const fields = [
  'industry',
  'audience',
  'services',
  'strengths',
  'businessName',
  'initials',
  'tagline',
  'brandIntro',
  'person',
  'role',
  'email',
  'phone',
  'website',
  'address',
  'cardLayout',
  'style',
  'accent',
];
const limits = {
  industry: 80,
  audience: 120,
  services: 400,
  strengths: 300,
  businessName: 60,
  initials: 4,
  tagline: 100,
  brandIntro: 400,
  person: 40,
  role: 60,
  email: 120,
  phone: 40,
  website: 240,
  address: 160,
};
const esc = (v) =>
  String(v || '').replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
  );
const clip = (value, max) => String(value || '').trim().slice(0, max);
const firstLine = (value) =>
  String(value || '')
    .split(/[,|\n/]/)[0]
    .trim();

function normalize(raw) {
  const b = Object.fromEntries(
    fields.map((k) => [k, clip(raw[k], limits[k] || 240)]),
  );
  b.accent = /^#[0-9a-f]{6}$/i.test(b.accent) ? b.accent : '#31594c';
  b.style = ['orbit', 'frame', 'wordmark'].includes(b.style) ? b.style : 'orbit';
  b.cardLayout = b.cardLayout === 'personal' ? 'personal' : 'company';
  const initialSource = clip(raw.initials, 20) || b.businessName;
  b.initials = Array.from(initialSource).slice(0, 4).join('') || 'AB';
  b.sample = raw.sample === true;
  return b;
}

/** Suggest tagline and brand intro from user-provided business facts only (no invented claims). */
function suggestCopy(raw) {
  const name = clip(raw.businessName, limits.businessName);
  const industry = clip(raw.industry, limits.industry);
  const audience = clip(raw.audience, limits.audience);
  const services = clip(raw.services, limits.services);
  const strengths = clip(raw.strengths, limits.strengths);

  let tagline = '';
  if (strengths) tagline = firstLine(strengths);
  else if (services) tagline = firstLine(services);
  else if (industry && audience) tagline = `${audience}을(를) 위한 ${industry}`;
  else if (industry) tagline = `${industry} 브랜드`;
  tagline = tagline.slice(0, limits.tagline);

  const intro = [];
  if (name && industry) intro.push(`${name}은(는) ${industry} 분야에서 활동합니다.`);
  if (audience) intro.push(`주요 고객은 ${audience}입니다.`);
  if (services) {
    const flat = services.replace(/\s*\n\s*/g, ' · ').slice(0, 200);
    intro.push(`제공: ${flat}.`);
  }
  if (strengths) {
    const flat = strengths.replace(/\s*\n\s*/g, ' · ').slice(0, 160);
    intro.push(`강점: ${flat}.`);
  }
  const brandIntro = intro.join(' ').slice(0, limits.brandIntro);

  return { tagline, brandIntro };
}

function applyCopySuggestions(raw, { overwrite = false } = {}) {
  const suggested = suggestCopy(raw);
  const next = { ...raw };
  if (overwrite || !clip(raw.tagline, limits.tagline)) next.tagline = suggested.tagline;
  if (overwrite || !clip(raw.brandIntro, limits.brandIntro)) next.brandIntro = suggested.brandIntro;
  return next;
}

function logo(raw) {
  const b = normalize(raw);
  const mark =
    b.style === 'wordmark'
      ? ''
      : b.style === 'frame'
        ? '<rect x="7" y="7" width="66" height="66" rx="12" fill="none" stroke="currentColor" stroke-width="4"/>'
        : '<circle cx="40" cy="40" r="32" fill="none" stroke="currentColor" stroke-width="4"/><circle cx="66" cy="20" r="7" fill="currentColor"/>';
  const nameLen = Array.from(b.businessName).length;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 100" role="img" aria-label="${esc(b.businessName || '브랜드')} 로고 초안"><g style="color:${b.accent}">${mark ? `<g transform="translate(0 10)">${mark}<text x="40" y="46" text-anchor="middle" font-family="system-ui,sans-serif" font-size="19" font-weight="700" fill="currentColor">${esc(b.initials)}</text></g>` : ''}<text x="${mark ? 95 : 10}" y="57" font-family="system-ui,sans-serif" font-size="${nameLen > 16 ? 16 : 27}" font-weight="700" fill="currentColor">${esc(b.businessName || '브랜드 이름')}</text></g></svg>`;
}

function introParagraph(b, maxLen) {
  const text = b.brandIntro || '';
  if (!text) return '';
  const shown = text.length > maxLen ? `${text.slice(0, maxLen)}…` : text;
  return `<p class="intro">${esc(shown)}</p>`;
}

function cardFront(b) {
  if (b.cardLayout === 'personal') {
    return `<article class="card front"><div class="person">${esc(b.person || '담당자 이름 입력 필요')}</div><p>${esc(b.role)}</p><p class="tagline">${esc(b.tagline || '소개 문구 입력 필요')}</p>${introParagraph(b, 120)}</article>`;
  }
  return `<article class="card front">${logo(b)}<p class="tagline">${esc(b.tagline || '소개 문구 입력 필요')}</p>${introParagraph(b, 200)}</article>`;
}

function cardBack(b) {
  const contact = [];
  if (b.email) contact.push(`<div><a href="mailto:${esc(b.email)}">${esc(b.email)}</a></div>`);
  if (b.phone) contact.push(`<div>${esc(b.phone)}</div>`);
  if (b.website) {
    const href = /^https?:\/\//i.test(b.website) ? b.website : `https://${b.website}`;
    contact.push(`<div><a href="${esc(href)}">${esc(b.website)}</a></div>`);
  }
  if (b.address) contact.push(`<div>${esc(b.address)}</div>`);
  const contactHtml = contact.length ? contact.join('') : '<div>연락 방법 입력 필요</div>';
  if (b.cardLayout === 'personal') {
    return `<article class="card back"><div><div class="person">${esc(b.businessName || '상호 입력 필요')}</div><p>${esc(b.industry)}</p></div><div class="details">${contactHtml}</div>${introParagraph(b, 280)}</article>`;
  }
  return `<article class="card back"><div><div class="person">${esc(b.person || '담당자 이름 입력 필요')}</div><p>${esc(b.role)}</p></div><div class="details">${contactHtml}</div>${introParagraph(b, 280)}</article>`;
}

function render(raw) {
  const b = normalize(raw);
  return `<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>*{box-sizing:border-box}body{margin:0;padding:24px;font-family:system-ui,sans-serif;color:#253d35;background:#e6eadd}h2{font-size:12px;margin:24px 0 12px}.logo{background:#fff;padding:24px;border-radius:12px}svg{width:100%;max-width:500px;height:auto}.card{min-height:240px;border-radius:12px;padding:30px;background:#fff;display:flex;flex-direction:column;justify-content:space-between;overflow-wrap:anywhere;word-break:keep-all}.front{border-top:6px solid ${b.accent}}.back{background:#253d35;color:#fff}.back a{color:#c8e8d8}.person{font-size:23px;font-weight:700}.tagline{font-size:15px;font-weight:600}.intro{font-size:13px;line-height:1.6;opacity:.92}.details{display:grid;gap:8px;font-size:13px}p{font-size:13px;line-height:1.6}@media(max-width:450px){body{padding:14px}.card{padding:22px}.person{font-size:20px}}</style><p>${b.sample ? '가상 예시 · 실제 사업 정보 아님' : '작성 중인 브랜드 초안'} · 공개·인쇄 전 확인 필요 · 실적·인증·가격은 입력하지 않은 항목을 만들지 않습니다</p><h2>01 / LOGO</h2><div class="logo">${logo(b)}</div><h2>02 / 명함 앞면 (${b.cardLayout === 'personal' ? '개인' : '회사'})</h2>${cardFront(b)}<h2>03 / 명함 뒷면</h2>${cardBack(b)}</html>`;
}

function collectGaps(b) {
  const gaps = [];
  if (!b.businessName) gaps.push('브랜드 이름');
  if (!b.industry) gaps.push('업종');
  if (!b.services) gaps.push('제공 서비스');
  if (!b.tagline && !b.brandIntro) gaps.push('소개·브랜드 문구');
  if (b.cardLayout === 'personal' && !b.person) gaps.push('담당자 이름');
  if (b.cardLayout === 'company' && !b.person) gaps.push('담당자(뒷면)');
  if (!b.email && !b.phone && !b.website) gaps.push('연락 방법');
  if (b.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(b.email)) gaps.push('이메일 형식');
  if (b.website && !/^https?:\/\/.+/i.test(b.website) && !/^[a-z0-9.-]+\.[a-z]{2,}/i.test(b.website)) {
    gaps.push('웹사이트 형식');
  }
  return gaps;
}

if (typeof module !== 'undefined') {
  module.exports = { normalize, logo, render, suggestCopy, applyCopySuggestions, collectGaps };
}
if (typeof document === 'undefined') return;

let id = new URLSearchParams(location.search).get('project');
let url;
const values = () => ({
  ...Object.fromEntries(fields.map((k) => [k, document.getElementById(k).value])),
  sample: document.getElementById('brand')?.dataset.sample === 'true',
});

function apply(b) {
  fields.forEach((k) => {
    if (b[k] != null && document.getElementById(k)) document.getElementById(k).value = b[k];
  });
  const form = document.getElementById('brand');
  if (form) form.dataset.sample = b.sample === true ? 'true' : 'false';
}

function update() {
  if (url) URL.revokeObjectURL(url);
  const v = values();
  url = URL.createObjectURL(new Blob([render(v)], { type: 'text/html;charset=utf-8' }));
  document.getElementById('preview').src = url;
  const b = normalize(v);
  const gaps = collectGaps(b);
  const root = document.getElementById('missing');
  root.replaceChildren();
  (gaps.length ? gaps.map((x) => `${x} 확인 필요`) : ['사업·연락 기본 입력 완료 · 상표·실제 연락처 확인 필요']).forEach((t) => {
    const li = document.createElement('li');
    li.textContent = t;
    root.append(li);
  });
}

const item = APFHomeServices.readProjects().find((p) => p.id === id && p.type === 'logo-card');
if (item?.brief) apply(item.brief);
else id = null;

fields.forEach((k) => {
  const el = document.getElementById(k);
  if (el) el.addEventListener('input', update);
});

document.getElementById('suggest-copy')?.addEventListener('click', () => {
  const merged = applyCopySuggestions(values(), { overwrite: false });
  apply(merged);
  document.getElementById('status').textContent =
    '입력하신 사업 정보만 반영해 빈 칸에 문구를 제안했습니다. 직접 수정할 수 있습니다.';
  update();
});

document.getElementById('example')?.addEventListener('click', () => {
  apply({
    industry: '브랜드·홈페이지 기획',
    audience: '처음 시작하는 소상공인',
    services: '브랜드 방향 정리\n홈페이지 초안 제작',
    strengths: '짧은 설명으로 이해하기 쉬운 구성',
    businessName: '온유 스튜디오',
    initials: 'ON',
    tagline: '생각을 정리하고, 브랜드를 만듭니다.',
    brandIntro:
      '온유 스튜디오는 브랜드·홈페이지 기획 분야에서 활동합니다. 주요 고객은 처음 시작하는 소상공인입니다.',
    person: '김예시',
    role: '브랜드 디자이너',
    email: 'hello@example.com',
    phone: '',
    website: 'https://example.com',
    address: '',
    cardLayout: 'company',
    style: 'orbit',
    accent: '#31594c',
    sample: true,
  });
  update();
});

document.getElementById('brand')?.addEventListener('submit', (e) => {
  e.preventDefault();
  try {
    const b = normalize(values());
    const saved = APFHomeServices.saveProject({
      id: id || undefined,
      type: 'logo-card',
      title: b.businessName,
      brief: { ...b, sample: values().sample },
      html: render(b),
      logo_svg: logo(b),
      creation_mode: 'rule_based_brand_studio',
      publish_ready: false,
    });
    id = saved.id;
    const q = new URLSearchParams();
    q.set('project', id);
    history.replaceState(null, '', `${location.pathname}?${q}`);
    document.getElementById('status').textContent =
      '이 브라우저에 초안을 저장했습니다. 현재 주소로 다시 열어 편집할 수 있습니다.';
  } catch {
    document.getElementById('status').textContent =
      '저장하지 못했습니다. 브라우저 저장 공간과 권한을 확인해 주세요.';
  }
});

update();
})();
