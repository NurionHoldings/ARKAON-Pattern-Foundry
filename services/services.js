(() => {
  const STORAGE_KEY = 'apf.home.projects.v1';
  const API_KEY = 'apf.home.apiBase.v1';
  const STUDIO_DRAFT_KEY = 'apf.co-creation.studio-drafts.v1';
  const REFERENCE_STASH_KEY = 'apf.reference-consent.stash.v1';
  const MAX_VIDEO_STORE_BYTES = 2.5 * 1024 * 1024;
  const URL_IN_TEXT = /https?:\/\/[^\s<>"']+/gi;

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function readProjects() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  }

  function writeProjects(items) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  }

  function readStudioDrafts() {
    try {
      const raw = localStorage.getItem(STUDIO_DRAFT_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch {
      return {};
    }
  }

  function writeStudioDrafts(map) {
    localStorage.setItem(STUDIO_DRAFT_KEY, JSON.stringify(map));
  }

  function loadCoCreationStudioDraft(sessionId) {
    if (!sessionId) return null;
    return readStudioDrafts()[sessionId] || null;
  }

  function saveCoCreationStudioDraft(sessionId, payload) {
    const map = readStudioDrafts();
    map[sessionId] = { ...payload, session_id: sessionId, updated_at: new Date().toISOString() };
    writeStudioDrafts(map);
    return map[sessionId];
  }

  function extractReferenceUrls(text) {
    const urls = String(text || '').match(URL_IN_TEXT) || [];
    return [...new Set(urls.map((u) => u.replace(/[.,)]+$/, '')))];
  }

  function buildStudioBriefFromWorkRequest({ title, message, scope }) {
    const combined = String(message || '');
    const fields = {
      title: String(title || '').trim(),
      audience: '',
      story: '',
      difference: '',
      contact: '',
    };
    const labelRules = [
      [/^(?:고객|대상\s*고객)[:：]\s*(.+)$/im, 'audience'],
      [/^(?:목적|서비스|하는\s*일)[:：]\s*(.+)$/im, 'story'],
      [/^(?:차별점|강점)[:：]\s*(.+)$/im, 'difference'],
      [/^(?:이름|브랜드|상호)[:：]\s*(.+)$/im, 'title'],
      [/^(?:연락|문의)[:：]\s*(.+)$/im, 'contact'],
    ];
    for (const line of combined.split('\n')) {
      for (const [pattern, key] of labelRules) {
        const match = line.trim().match(pattern);
        if (match && !fields[key]) fields[key] = match[1].trim();
      }
    }
    if (!fields.title) {
      const first = combined.split('\n').map((l) => l.trim()).find(Boolean);
      fields.title = first ? first.slice(0, 80) : '새 홈페이지';
    }
    if (!fields.audience) fields.audience = `${fields.title}를 찾는 방문자`;
    if (!fields.story) fields.story = combined.trim().slice(0, 2000) || fields.title;
    if (!fields.difference) {
      fields.difference = `${fields.title}는 ${fields.audience}에게 맞춘 읽기 쉬운 구성을 우선합니다.`;
    }
    if (!fields.contact) {
      fields.contact = '공개 전에 스튜디오 화면에서 이메일·전화·상담 채널을 확인·수정할 수 있습니다.';
    }
    let industry = 'service';
    if (/포트폴리오|프리랜|작업\s*소개/i.test(combined)) industry = 'portfolio';
    else if (/가게|매장|카페|메뉴|상품/i.test(combined)) industry = 'shop';
    else if (scope === 'PLATFORM') industry = 'service';
    const offerings = [
      `핵심 ${industry === 'shop' ? '메뉴' : '서비스'} | ${fields.story.slice(0, 80)}`,
      `맞춤 구성 | ${fields.audience}에 맞춘 설명과 화면 구조`,
      `확인·수정 | 초안을 보고 함께 다듬는 단계`,
    ].join('\n');
    const process = ['목적과 범위 확인', '구성·디자인 방향 협의', '초안 공유 후 수정·확정'].join('\n');
    return {
      industry,
      title: fields.title,
      audience: fields.audience,
      story: fields.story,
      offerings,
      difference: fields.difference,
      process,
      contact: fields.contact,
      theme: 'editorial',
    };
  }

  function stashReferenceConsentResume(payload) {
    sessionStorage.setItem(REFERENCE_STASH_KEY, JSON.stringify({ ...payload, saved_at: new Date().toISOString() }));
  }

  function popReferenceConsentStash() {
    try {
      const raw = sessionStorage.getItem(REFERENCE_STASH_KEY);
      if (!raw) return null;
      sessionStorage.removeItem(REFERENCE_STASH_KEY);
      return resumeCoCreationStash(JSON.parse(raw));
    } catch {
      return null;
    }
  }

  function resumeCoCreationStash(stash) {
    if (!stash || typeof stash !== 'object') return null;
    if (!stash.brief && stash.title && stash.message) {
      stash.brief = buildStudioBriefFromWorkRequest({
        title: stash.title,
        message: stash.message,
        scope: stash.scope || 'LANDING',
      });
    }
    return stash;
  }

  function readCsrfToken() {
    const match = document.cookie.split('; ').find((row) => row.startsWith('apf_console_csrf='));
    return match ? decodeURIComponent(match.split('=').slice(1).join('=')) : '';
  }

  function getApiOrigin() {
    const base = getApiBase();
    if (!base) return null;
    try {
      return new URL(base).origin;
    } catch {
      return null;
    }
  }

  function canConsoleApiSync() {
    const apiOrigin = getApiOrigin();
    if (!apiOrigin) return false;
    return apiOrigin === window.location.origin;
  }

  async function consoleApiFetch(path, options = {}) {
    const base = getApiBase();
    if (!base) throw new Error('API_NOT_CONFIGURED');
    const method = (options.method || 'GET').toUpperCase();
    const headers = { ...(options.headers || {}) };
    if (method !== 'GET' && method !== 'HEAD') {
      if (!canConsoleApiSync()) {
        throw new Error('API_CROSS_ORIGIN');
      }
      const token = readCsrfToken();
      if (!token) throw new Error('CSRF_TOKEN_MISSING');
      headers['X-CSRF-Token'] = token;
    }
    return fetch(`${base}${path}`, { ...options, credentials: 'include', headers });
  }

  async function fetchCoCreationStudioDraft(sessionId) {
    if (!sessionId || !canConsoleApiSync()) return null;
    try {
      const response = await consoleApiFetch(
        `/v1/console/co-creation/studio/${encodeURIComponent(sessionId)}`,
        { method: 'GET' },
      );
      if (!response.ok) return null;
      const body = await response.json();
      return body.draft || null;
    } catch {
      return null;
    }
  }

  function saveProject(entry) {
    const items = readProjects();
    const id = entry.id || crypto.randomUUID();
    const next = { ...entry, id, updated_at: new Date().toISOString() };
    const index = items.findIndex((item) => item.id === id);
    if (index >= 0) items[index] = next;
    else items.unshift(next);
    writeProjects(items);
    return next;
  }

  function downloadText(filename, content, type = 'text/html;charset=utf-8') {
    const url = URL.createObjectURL(new Blob([content], { type }));
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 500);
  }

  function siteHtml({ title, tagline, body, accent, email, phone }) {
    const safeTitle = escapeHtml(title || '내 홈페이지');
    const safeTag = escapeHtml(tagline || '');
    const safeBody = escapeHtml(body || '').replace(/\n/g, '<br>');
    const safeEmail = escapeHtml(email || '');
    const safePhone = escapeHtml(phone || '');
    const color = /^#[0-9a-fA-F]{6}$/.test(accent || '') ? accent : '#5cbad8';
    return `<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${safeTitle}</title><style>body{margin:0;font-family:system-ui,sans-serif;background:#0a1220;color:#eef3ff;line-height:1.7}.wrap{max-width:720px;margin:auto;padding:48px 24px}h1{font-size:2rem;color:${color}}.tag{color:#9eb2c8}a{color:${color}}</style><div class="wrap"><h1>${safeTitle}</h1><p class="tag">${safeTag}</p><p>${safeBody}</p><p>${safeEmail ? `<a href="mailto:${safeEmail}">${safeEmail}</a>` : ''}${safePhone ? ` · ${safePhone}` : ''}</p><footer style="margin-top:48px;font-size:.85rem;color:#7a8fa6">아르카온 홈페이지 만들기로 생성</footer></div></html>`;
  }

  function personalPageHtml({ handle, displayName, bio, linksText, accent }) {
    const safeHandle = escapeHtml(handle || 'me');
    const safeName = escapeHtml(displayName || safeHandle);
    const safeBio = escapeHtml(bio || '').replace(/\n/g, '<br>');
    const color = /^#[0-9a-fA-F]{6}$/.test(accent || '') ? accent : '#ad79ff';
    const links = String(linksText || '')
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const [label, url] = line.includes('|') ? line.split('|').map((x) => x.trim()) : [line, line];
        const href = escapeHtml(url);
        return `<li><a href="${href}" rel="noopener noreferrer">${escapeHtml(label)}</a></li>`;
      })
      .join('');
    return `<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${safeName} · @${safeHandle}</title><style>body{margin:0;font-family:system-ui,sans-serif;background:#080f1d;color:#e7eef9}.wrap{max-width:520px;margin:auto;padding:56px 24px;text-align:center}h1{font-size:1.75rem;margin-bottom:8px}.handle{color:${color};letter-spacing:.06em}ul{list-style:none;padding:0;margin:24px 0}li{margin:10px 0}a{color:${color}}</style><div class="wrap"><p class="handle">@${safeHandle}</p><h1>${safeName}</h1><p>${safeBio}</p><ul>${links}</ul></div></html>`;
  }

  function businessCardHtml({ businessName, role, email, phone, accent }) {
    const color = /^#[0-9a-fA-F]{6}$/.test(accent || '') ? accent : '#75d8f9';
    return `<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escapeHtml(businessName)} 명함</title><style>body{margin:0;display:grid;place-items:center;min-height:100svh;background:#0a1220;font-family:system-ui,sans-serif}.card{width:min(420px,92vw);aspect-ratio:1.75;border-radius:16px;padding:28px;background:linear-gradient(145deg,#101e30,#0a1524);border:1px solid ${color};color:#eef3ff}h1{margin:0 0 8px;font-size:1.5rem;color:${color}}p{margin:4px 0;color:#b8c8de}a{color:${color}}</style><article class="card"><h1>${escapeHtml(businessName)}</h1><p>${escapeHtml(role || '')}</p><p>${email ? `<a href="mailto:${escapeHtml(email)}">${escapeHtml(email)}</a>` : ''}</p><p>${escapeHtml(phone || '')}</p></article></html>`;
  }

  function getApiBase() {
    const stored = localStorage.getItem(API_KEY);
    return stored ? stored.replace(/\/$/, '') : '';
  }

  function setApiBase(value) {
    const trimmed = String(value || '').trim().replace(/\/$/, '');
    if (trimmed) localStorage.setItem(API_KEY, trimmed);
    else localStorage.removeItem(API_KEY);
  }

  async function probeApi(base) {
    if (!base) return { ok: false, reason: 'not_configured' };
    try {
      const response = await fetch(`${base}/health`, { method: 'GET', credentials: 'omit' });
      return { ok: response.ok, status: response.status };
    } catch {
      return { ok: false, reason: 'network' };
    }
  }

  function readFileAsDataUrl(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ''));
      reader.onerror = () => reject(reader.error || new Error('read failed'));
      reader.readAsDataURL(file);
    });
  }

  async function saveVideoUpload(file, { title } = {}) {
    if (!file || !String(file.type || '').startsWith('video/')) {
      throw new Error('VIDEO_TYPE');
    }
    const entry = {
      type: 'ai-video-upload',
      title: title || file.name.replace(/\.[^.]+$/, '') || '업로드 영상',
      fileName: file.name,
      mimeType: file.type,
      byteSize: file.size,
    };
    if (file.size <= MAX_VIDEO_STORE_BYTES) {
      entry.videoDataUrl = await readFileAsDataUrl(file);
    }
    return saveProject(entry);
  }

  function downloadDataUrl(filename, dataUrl) {
    const anchor = document.createElement('a');
    anchor.href = dataUrl;
    anchor.download = filename;
    anchor.click();
  }

  window.APFHomeServices = {
    escapeHtml,
    readProjects,
    saveProject,
    downloadText,
    downloadDataUrl,
    siteHtml,
    personalPageHtml,
    businessCardHtml,
    getApiBase,
    setApiBase,
    probeApi,
    saveVideoUpload,
    loadCoCreationStudioDraft,
    saveCoCreationStudioDraft,
    buildStudioBriefFromWorkRequest,
    extractReferenceUrls,
    stashReferenceConsentResume,
    popReferenceConsentStash,
    resumeCoCreationStash,
    readCsrfToken,
    getApiOrigin,
    canConsoleApiSync,
    consoleApiFetch,
    fetchCoCreationStudioDraft,
    MAX_VIDEO_STORE_BYTES,
  };
})();
