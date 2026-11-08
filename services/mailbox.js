(() => {
  const status = document.getElementById('mailboxStatus');
  const button = document.getElementById('refreshMailbox');
  const root = document.getElementById('mailboxItems');
  const base = APFHomeServices.getApiBase();
  if (base) document.getElementById('mailboxConsole').href = `${base}/console`;
  else status.textContent = 'Foundry API 주소가 설정되지 않아 실시간 우편함을 확인할 수 없습니다. 연결 설정 후 운영 콘솔에 로그인해 주세요.';
  button.addEventListener('click', async () => {
    if (!base) { status.textContent = '연결 설정에서 Foundry API 주소를 먼저 입력해 주세요. 미연결 상태는 제안 0건을 뜻하지 않습니다.'; return; }
    button.disabled = true;
    root.replaceChildren();
    status.textContent = '수정·진화 제안을 확인하고 있습니다…';
    try {
      const response = await fetch(`${base}/v1/console/mailbox`, {credentials:'include',redirect:'error',signal:AbortSignal.timeout(15000)});
      if ([401,403].includes(response.status)) throw new Error('SESSION');
      if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) throw new Error('RESPONSE');
      const items = await response.json();
      if (!Array.isArray(items)) throw new Error('RESPONSE');
      const pending = items.filter(item => item && !['FULFILLED','COMPLETED','ARCHIVED'].includes(item.status));
      status.textContent = `전체 ${items.length}건 · 검토 대상 ${pending.length}건 (최대 30건 표시)`;
      for (const item of pending.slice(0,30)) {
        const li = document.createElement('li');
        const summary = document.createElement('span');summary.textContent = String(item.summary || '요약 없음').slice(0,2000);
        const state = document.createElement('span');state.className='chip';state.textContent=String(item.status || '상태 미확인');
        li.append(summary,state);root.append(li);
      }
    } catch(error) {
      status.textContent = error.message === 'SESSION'
        ? '운영 콘솔 로그인이 필요하거나 조회 권한이 없습니다.'
        : '우편함을 조회하지 못했습니다. 서버 주소·로그인·연결 허용 설정을 확인해 주세요. 제안 유무는 아직 확인되지 않았습니다.';
    } finally { button.disabled = false; }
  });
})();
