(() => {
  const GAP = {
    API_HEALTH_MISSING: {
      severity: 'BLOCKER',
      summary: 'Foundry API /health에 연결되지 않습니다.',
      needed_from_admin:
        '범: Foundry API를 기동하거나 Netlify·리버스 프록시로 /health·/console을 공개 호스트와 연결해 주세요.',
      assignee: 'beom',
      self_heal_step: 'account에 API URL 설정 후 연결 확인',
    },
    API_CONSOLE_UNREACHABLE: {
      severity: 'BLOCKER',
      summary: '운영 콘솔(/console) 경로에 접근할 수 없습니다.',
      needed_from_admin: '범: /console을 Foundry와 동일 출처로 노출하거나 관리자 URL을 안내해 주세요.',
      assignee: 'beom',
      self_heal_step: 'admin·account API 설정',
    },
    CO_CREATE_NOT_WIRED: {
      severity: 'HIGH',
      summary: '공동 창작 API가 공개 UI에 연결되어 있지 않습니다.',
      needed_from_admin:
        '범: /v1/console/co-creation/chat 세션·UI 연동 또는 co-create 페이지에서 API 호출을 구현해 주세요.',
      assignee: 'beom',
      self_heal_step: 'Foundry dev session + co-create POST',
    },
    FOUNDRY_PROXY_NOT_CONFIGURED: {
      severity: 'HIGH',
      summary: 'Netlify Functions에 APF_API_ORIGIN이 설정되지 않았거나 프록시가 배포되지 않았습니다.',
      needed_from_admin: '범: Render API 공개 URL 확정 후 Netlify Functions 범위에 APF_API_ORIGIN을 설정해 주세요.',
      assignee: 'beom',
      self_heal_step: 'docs/70-operational-connect-rollout.md 5단계',
    },
    UX_CLAIM_MISMATCH: {
      severity: 'MEDIUM',
      summary: '「이용 가능」 표시와 실제 API·결제·게시 기능 간 간극이 있습니다.',
      needed_from_admin:
        '에테르니언: 카피·상태 배지 정합 검토. 범: API·과금·게시 로드맵 우선순위.',
      assignee: 'eternian',
      self_heal_step: '카탈로그 status·홈 카드 문구 조정',
    },
  };

  async function probeHealth(base) {
    try {
      const response = await fetch(`${base.replace(/\/$/, '')}/health`, {
        method: 'GET',
        credentials: 'same-origin',
        cache: 'no-store',
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  async function probeConsole(base) {
    try {
      const response = await fetch(`${base.replace(/\/$/, '')}/console`, {
        method: 'GET',
        credentials: 'same-origin',
        cache: 'no-store',
        redirect: 'manual',
      });
      return response.status === 200 || response.status === 302 || response.status === 401;
    } catch {
      return false;
    }
  }

  async function runDiagnosis() {
    const resolveBase = window.APFHomeServices?.resolveApiBase?.bind(window.APFHomeServices);
    const base = resolveBase ? resolveBase() : window.location.origin;
    const findings = [];

    const healthOk = await probeHealth(base);
    const consoleOk = await probeConsole(base);
    if (!healthOk && base.includes('netlify.app')) {
      findings.push({ gap_code: 'FOUNDRY_PROXY_NOT_CONFIGURED', ...GAP.FOUNDRY_PROXY_NOT_CONFIGURED });
    }
    if (!healthOk) findings.push({ gap_code: 'API_HEALTH_MISSING', ...GAP.API_HEALTH_MISSING });
    if (!consoleOk) findings.push({ gap_code: 'API_CONSOLE_UNREACHABLE', ...GAP.API_CONSOLE_UNREACHABLE });
    findings.push({ gap_code: 'CO_CREATE_NOT_WIRED', ...GAP.CO_CREATE_NOT_WIRED });
    findings.push({ gap_code: 'UX_CLAIM_MISMATCH', ...GAP.UX_CLAIM_MISMATCH });

    const seen = new Set();
    return findings.filter((item) => {
      if (seen.has(item.gap_code)) return false;
      seen.add(item.gap_code);
      return true;
    });
  }

  async function submitReport(findings) {
    const payload = {
      platform_id: 'ARKAON_FOUNDRY',
      surface_url: window.location.href,
      include_static_assessment: true,
      findings: findings.map(({ gap_code, severity, summary, needed_from_admin, self_heal_step, assignee }) => ({
        gap_code,
        severity,
        summary,
        needed_from_admin,
        self_heal_step,
        assignee,
      })),
    };
    const apiBase = window.APFHomeServices?.resolveApiBase?.() || window.location.origin;
    const targets = [`${apiBase.replace(/\/$/, '')}/v1/public/platform-self-heal`];
    for (const url of targets) {
      try {
        const response = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (response.ok) return { ok: true, body: await response.json(), channel: url };
        if (response.status !== 404) return { ok: false, status: response.status, channel: url };
      } catch {
        /* try next */
      }
    }
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `arkaon-self-heal-${Date.now()}.json`;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 500);
    window.APFHomeServices?.saveProject?.({
      type: 'self-heal-report',
      title: `자가치유 ${findings.length}건`,
      html: '',
      report: payload,
    });
    return { ok: false, downloaded: true };
  }

  window.APFPlatformSelfHeal = { runDiagnosis, submitReport };
})();
