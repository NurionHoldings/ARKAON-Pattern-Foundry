/* Server-created fields only. Call from the host's authenticated, CSRF-protected UI. */
export async function openHectoCheckout(platform, businessOrderId, csrfToken) {
  const response = await fetch(`/v1/payments/hecto/${encodeURIComponent(platform)}/checkout`, {
    method: 'POST', credentials: 'same-origin',
    headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken},
    body: JSON.stringify({business_order_id: businessOrderId})
  });
  if (!response.ok) throw new Error('결제를 시작하지 못했습니다. 주문 상태를 확인해 주세요.');
  const payload = await response.json();
  if (payload.action !== 'https://tbnpg.settlebank.co.kr/card/main.do' || payload.method !== 'POST') {
    throw new Error('허용되지 않은 결제 환경입니다.');
  }
  const form = document.createElement('form');
  form.method = 'POST'; form.action = payload.action; form.acceptCharset = 'UTF-8';
  const allowed = new Set(['mchtId','method','mchtTrdNo','mchtName','pmtPrdtNm','trdDt','trdTm',
    'trdAmt','notiUrl','nextUrl','cancUrl','pktHash']);
  for (const [name, value] of Object.entries(payload.fields)) {
    if (!allowed.has(name) || typeof value !== 'string') throw new Error('결제 정보 형식 오류');
    const input = document.createElement('input');
    input.type = 'hidden'; input.name = name; input.value = value; form.append(input);
  }
  document.body.append(form); form.submit(); // top-level POST; no iframe/pop-up dependency
}
// Return page: ignore query outStatCd. GET authenticated order status from the server.
// PENDING means '결제 확인 중'; PAID means '결제 확인 완료'. Never grant access here.
