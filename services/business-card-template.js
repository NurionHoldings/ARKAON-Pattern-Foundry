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
    if(!['single','double'].includes(input.sides))return svg.replace('</svg>',extra+'</svg>');
    const width=Number(template.match(/data-face-width="(\d+)"/)?.[1])||550,height=Number(template.match(/data-face-height="(\d+)"/)?.[1])||305;
    const find=side=>svg.match(new RegExp(`<g data-card-face="${side}"[^>]*>([\\s\\S]*?)</g>`))?.[1]||'';
    const x=Number(template.match(/data-contact-x="(\d+)"/)?.[1])||305,y=Number(template.match(/data-contact-y="(\d+)"/)?.[1])||196;
    const contacts=`<text x="${x}" y="${y}" fill="${ink}" font-family="Noto Sans CJK KR,sans-serif" font-size="11">${escape(input.email)}</text><text x="${x}" y="${y+25}" fill="${ink}" font-family="Noto Sans CJK KR,sans-serif" font-size="11">${escape(input.phone)}</text>`;
    const front=find('front'),back=find('back')+contacts;
    const singleTagline=`<text x="35" y="${height-12}" fill="${ink}" font-family="Noto Sans CJK KR,sans-serif" font-size="9">${escape(input.tagline)}</text>`;
    const faces=input.sides==='single'?[{name:'front',label:'단면 · 정보면',body:back+singleTagline}]:[{name:'front',label:'앞면',body:front},{name:'back',label:'뒷면',body:back}];
    return `<svg xmlns="http://www.w3.org/2000/svg" font-family="Noto Sans CJK KR,Malgun Gothic,sans-serif" width="${(width+30)*faces.length+20}" height="${height+65}" viewBox="0 0 ${(width+30)*faces.length+20} ${height+65}" data-card-sides="${input.sides}" data-face-width="${width}" data-face-height="${height}">${faces.map((face,i)=>`<text x="${20+i*(width+30)}" y="23" font-size="14" font-family="Noto Sans CJK KR,sans-serif" fill="#263b33">${face.label}</text><g data-card-rendered="${face.name}" transform="translate(${20+i*(width+30)} 40)">${face.body}</g>`).join('')}</svg>`;

  }
  function faceSvg(svg,side){
    const width=Number(svg.match(/data-face-width="(\d+)"/)?.[1])||550,height=Number(svg.match(/data-face-height="(\d+)"/)?.[1])||305;
    const body=svg.match(new RegExp(`<g data-card-rendered="${side}"[^>]*>([\\s\\S]*?)</g>`))?.[1];
    return body?`<svg xmlns="http://www.w3.org/2000/svg" font-family="Noto Sans CJK KR,Malgun Gothic,sans-serif" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">${body}</svg>`:'';
  }
  function documentHtml(svg){
    const mode=svg.match(/data-card-sides="(single|double)"/)?.[1];
    const content=mode?['front',...(mode==='double'?['back']:[])].map(side=>`<section><h2>${mode==='single'?'단면 · 정보면':side==='front'?'앞면':'뒷면'}</h2>${faceSvg(svg,side)}</section>`).join(''):svg;
    return `<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>명함 디자인</title><style>body{margin:0;background:#e6ebe2;color:#263b33;font-family:"Noto Sans CJK KR","Malgun Gothic",sans-serif}.art{width:min(100%,1000px);margin:auto;padding:28px;box-sizing:border-box}section{margin-bottom:28px}h2{font-size:11px;font-weight:550;letter-spacing:.1em;margin:0 0 12px;color:#52694f}svg{display:block;width:100%;height:auto;box-shadow:0 12px 28px #243c3315}@media print{body{background:white}.art{padding:0}section{break-after:page}h2{display:none}}</style><main class="art">${content}</main></html>`;
  }
  return {compose,documentHtml,faceSvg};
});
