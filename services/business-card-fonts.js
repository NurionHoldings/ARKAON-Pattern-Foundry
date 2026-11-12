/* Font uploads stay in the browser. Only validated font data enters SVG/CSS. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.APFCardFonts=api;})(typeof window==='undefined'?globalThis:window,()=>{
  const maxBytes=10*1024*1024;
  const presets=[
    {id:'default',name:'기본 고딕 · 또렷하고 간결한',family:'sans-serif'},
    {id:'gothic',name:'나눔고딕 · 단정한 비즈니스',file:'NanumGothic-Regular.woff2'},
    {id:'myeongjo',name:'나눔명조 · 정제된 클래식',file:'NanumMyeongjo-Regular.woff2'},
    {id:'pen',name:'나눔손글씨 펜 · 자연스러운 감성',file:'NanumPenScript-Regular.woff2'},
  ];
  function inspect(bytes,name){
    if(!bytes.length||bytes.length>maxBytes)throw Error('글꼴 파일은 10MB 이하로 선택해 주세요.');
    const signature=String.fromCharCode(...bytes.slice(0,4));
    const format=signature==='wOF2'?'woff2':signature==='wOFF'?'woff':signature==='OTTO'?'opentype':bytes[0]===0&&bytes[1]===1&&bytes[2]===0&&bytes[3]===0?'truetype':null;
    const ext=String(name).split('.').pop().toLowerCase();
    if(!format||!({ttf:'truetype',otf:'opentype',woff:'woff',woff2:'woff2'})[ext]||({ttf:'truetype',otf:'opentype',woff:'woff',woff2:'woff2'})[ext]!==format)throw Error('TTF·OTF·WOFF·WOFF2 형식의 올바른 글꼴 파일을 선택해 주세요.');
    return format;
  }
  function valid(font){return font&&['woff2','woff','opentype','truetype'].includes(font.format)&&typeof font.dataUrl==='string'&&font.dataUrl.length<=Math.ceil(maxBytes/3)*4+80&&/^data:font\/(?:ttf|otf|woff|woff2);base64,[A-Za-z0-9+/]+={0,2}$/.test(font.dataUrl);}
  function style(font){return valid(font)?`@font-face{font-family:APFCardFont;src:url("${font.dataUrl}") format("${font.format}");font-weight:100 900;font-style:normal}text{font-family:APFCardFont,"Noto Sans CJK KR",sans-serif!important}`:'';}
  return {maxBytes,presets,inspect,valid,style};
});
