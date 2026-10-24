/* Versioned element controls and bounded, session-local edit history. */
(() => {
  'use strict';
  const escape=v=>String(v||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function number(value,fallback,min,max){const n=value===''||value==null?fallback:Number(value);return Number.isFinite(n)?Math.max(min,Math.min(max,n)):fallback;}
  function normalize(raw){return {elementModelVersion:1,symbolSize:number(raw.symbolSize,80,40,100),logoGap:number(raw.logoGap,16,8,64),letterSpacing:number(raw.letterSpacing,0,0,4),logoAlign:['left','center','right'].includes(raw.logoAlign)?raw.logoAlign:'left'};}
  function compose(raw,mark,label){
    const e=normalize(raw);let mode=['horizontal','stacked','symbol'].includes(raw.logoLockup)?raw.logoLockup:'horizontal';
    if(!mark&&mode==='symbol')mode='horizontal';
    const color=raw.logoTone==='dark'?'#ffffff':raw.logoTone==='mono'?'#172b24':/^#[0-9a-f]{6}$/i.test(raw.accent||'')?raw.accent:'#31594c';
    const name=Array.from(String(raw.businessName||'브랜드 이름')).slice(0,60);
    const width=mode==='horizontal'?480:mode==='stacked'?320:120;
    const textStart=mode==='horizontal'&&mark?24+e.symbolSize+e.logoGap:24;
    const available=width-textStart-24,font=20,lineHeight=27;
    const chunk=Math.max(1,Math.floor(available/(font+e.letterSpacing)));
    const lines=[];for(let i=0;i<name.length;i+=chunk)lines.push(name.slice(i,i+chunk).join(''));
    const textHeight=lines.length*lineHeight;
    const textTop=mode==='stacked'&&mark?24+e.symbolSize+e.logoGap:24;
    const height=mode==='symbol'?120:Math.max(140,textTop+textHeight+24);
    const symbolX=mode==='horizontal'?24:(width-e.symbolSize)/2;
    const symbolY=mode==='stacked'?24:(height-e.symbolSize)/2;
    const anchor={left:'start',center:'middle',right:'end'}[e.logoAlign];
    const textX=e.logoAlign==='left'?textStart:e.logoAlign==='center'?textStart+available/2:width-24;
    const text=mode==='symbol'?'':lines.map((line,i)=>`<text x="${textX}" y="${textTop+font+i*lineHeight}" text-anchor="${anchor}" font-family="system-ui,sans-serif" font-size="${font}" letter-spacing="${e.letterSpacing}" font-weight="700" fill="${color}">${escape(line)}</text>`).join('');
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escape(raw.businessName||'브랜드')} ${escape(label)} 로고 초안" data-element-model="1" data-symbol-size="${e.symbolSize}" data-logo-gap="${e.logoGap}" data-logo-align="${e.logoAlign}">${mark?`<g color="${color}" transform="translate(${symbolX} ${symbolY}) scale(${e.symbolSize/100})">${mark}</g>`:''}${text}</svg>`;
  }
  function history(initial,limit=10){
    const copy=x=>JSON.parse(JSON.stringify(x));
    let states=[copy(initial)],index=0;
    return {
      push(value){if(JSON.stringify(value)===JSON.stringify(states[index]))return;states=states.slice(0,index+1);states.push(copy(value));if(states.length>limit+1)states.shift();index=states.length-1;},
      undo(){if(index>0)index--;return copy(states[index]);},
      redo(){if(index<states.length-1)index++;return copy(states[index]);},
      get canUndo(){return index>0;},get canRedo(){return index<states.length-1;},
    };
  }
  const api={normalize,compose,history};if(typeof module!=='undefined')module.exports=api;
  if(typeof window!=='undefined')window.APFBrandEditing=api;
})();
