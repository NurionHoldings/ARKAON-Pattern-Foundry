/* Independently implemented foundations measured from owner-selected public sites. */
(() => {
 'use strict';
 const presets=Object.freeze([
  Object.freeze({id:'dapanda',label:'다판다형 · 차콜과 골드',summary:'넓은 소개 · 탐색 카드 · 정보 구역',background:'#0b0b0a',accent:'#e3c46d'}),
  Object.freeze({id:'arirang',label:'더아리랑형 · 블루와 청회색',summary:'블루 소개 · 목적별 3카드 · 정보 패널',background:'#f3f6fc',accent:'#285998'}),
 ]);
 const css={
 dapanda:`.dapanda{--bg:#0b0b0a;--ink:#f5f2e9;--muted:#b5b1a7;--panel:#171715;--line:#37362f;--accent:#e3c46d}.dapanda .wrap{max-width:1280px;padding:0 4%}.dapanda .hero{background:linear-gradient(120deg,#292519,#171610 70%);border:1px solid var(--line);border-radius:18px;padding:52px 5%;margin:28px 0;gap:6%;grid-template-columns:1.25fr .75fr}.dapanda .visual{aspect-ratio:1/1;border-radius:16px;background:#22221f;color:#e3c46d}.dapanda .cta{color:#19170e}.dapanda .offer{border:1px solid var(--line);border-radius:14px}.dapanda .offers{gap:20px}.dapanda .section{padding:40px 0}`,
 arirang:`.arirang{--bg:#f3f6fc;--ink:#1c3352;--muted:#455c79;--panel:#ffffff;--line:#dbe3ee;--accent:#285998}.arirang .wrap{max-width:1440px;padding:0 4%}.arirang .nav{background:#fff;padding:24px;border-radius:0 0 12px 12px}.arirang .hero{background:linear-gradient(115deg,#163b70,#285998);color:#fff;border-radius:24px;padding:48px 4%;margin:28px 0;gap:5%;grid-template-columns:1.4fr .6fr}.arirang .hero p,.arirang .hero small,.arirang .hero .eyebrow{color:#e5edf9}.arirang .hero .cta{background:#fff;color:#163b70}.arirang .visual{aspect-ratio:1/1;border-radius:22px;background:#ffffff12;border:1px solid #ffffff40}.arirang .visual:before,.arirang .visual:after{display:none}.arirang .offers{grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}.arirang .offer{background:#eaf3e8;border-top:4px solid #2c644b;border-radius:16px}.arirang .offer:nth-child(3n+2){background:#ecf2fc;border-color:#285998}.arirang .offer:nth-child(3n){background:#fff0e9;border-color:#a54d43}.arirang .about,.arirang .contact{background:#fff;border-radius:18px;padding:28px}.arirang .process li{background:#fff;padding:20px;border-radius:12px}.arirang footer{background:#e9f0fc;padding:28px}`,
 };
 function validTheme(value){return ['editorial','night','minimal',...presets.map(x=>x.id)].includes(value);}
 function styles(id){return Object.hasOwn(css,id)?css[id]+`@media(max-width:650px){.${id} .hero{grid-template-columns:1fr;padding:30px 22px;gap:24px}.${id} .offers,.${id} .about{grid-template-columns:1fr}.${id} .visual{aspect-ratio:auto;height:150px}.${id} .nav{flex-wrap:wrap;overflow-wrap:anywhere}.${id} .links{flex-wrap:wrap}.${id} .wrap{padding:0 5%}}`:'';}
 const api={presets,validTheme,styles};
 if(typeof module!=='undefined')module.exports=api;
 if(typeof window!=='undefined')window.APFPlatformPresets=api;
})();
