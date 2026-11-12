/* Trusted local SVG layouts; all editable text is XML-escaped before insertion. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.APFCardTemplate=api;})(typeof window==='undefined'?globalThis:window,()=>{
  const escape=value=>String(value||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function compose(template,input,palette){
    const text={
      '(주)아르카온':input.businessName,'홍길동':input.personName,
      '담당자 · 이름 표기 예시':input.role,'상상에 형태를. 가능성에 생명력을.':input.tagline,
      'www.아르카온.com':input.website,'서울 서초구 방배동 952-2':input.address,
      '디엠그레이스서초 1102호':input.addressDetail,
    };
    const colors={[palette.background]:input.background,[palette.ink]:input.ink,[palette.accent]:input.accent};
    let svg=template.replace(/#[0-9a-f]{6}/gi,value=>colors[value]&&/^#[0-9a-f]{6}$/i.test(colors[value])?colors[value]:value);
    svg=svg.replace(/\(주\)아르카온|홍길동|담당자 · 이름 표기 예시|상상에 형태를\. 가능성에 생명력을\.|www\.아르카온\.com|서울 서초구 방배동 952-2|디엠그레이스서초 1102호/g,value=>escape(text[value]));
    const ink=/^#[0-9a-f]{6}$/i.test(input.ink)?input.ink:palette.ink;
    const extra=`<g transform="translate(405 290)" font-family="Noto Sans CJK KR,sans-serif" fill="${ink}" font-size="10"><text x="305" y="196">${escape(input.email)}</text><text x="305" y="221">${escape(input.phone)}</text></g>`;
    return svg.replace('</svg>',extra+'</svg>');
  }
  function documentHtml(svg){return `<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>명함 디자인</title><style>body{margin:0;background:#d8d7d2;display:grid;place-items:center;min-height:100vh}.art{width:min(100%,1200px)}svg{display:block;width:100%;height:auto}@media print{body{background:white}}</style><main class="art">${svg}</main></html>`;}
  return {compose,documentHtml};
});
