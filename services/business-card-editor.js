(() => {
  const catalog=APFCardCatalog;
  const labels=catalog.map(item=>item.name);
  const palettes=catalog.map(item=>item.palette);
  const fields=['businessName','personName','role','tagline','website','address','addressDetail','email','phone','sides','background','ink','accent'];
  const grid=document.getElementById('cardSampleGrid'),status=document.getElementById('cardEditorStatus'),preview=document.getElementById('preview');
  let selected=0,template='',generation=0,activeFont=null,uploadedFont=null,fontGeneration=0,fontBusy=false;
  const presetCache=new Map(),fontSelect=document.getElementById('cardFontSelect'),fontStatus=document.getElementById('cardFontStatus');
  const values=()=>({...Object.fromEntries(fields.map(id=>[id,document.getElementById(id).value])),cardFont:activeFont});
  const svg=()=>APFCardTemplate.compose(template,values(),palettes[selected]);
  function sizePreview(){
    if(!template)return;
    const width=Number(template.match(/data-face-width="(\d+)"/)?.[1])||550,height=Number(template.match(/data-face-height="(\d+)"/)?.[1])||305;
    const count=document.getElementById('sides').value==='single'?1:2;
    preview.style.height=`${Math.min(1100,Math.max(280,56+count*((Math.max(180,preview.clientWidth-56)*height/width)+53)))}px`;
  }
  new ResizeObserver(sizePreview).observe(preview);
  function render(){sizePreview();if(template)preview.srcdoc=APFCardTemplate.documentHtml(svg());document.getElementById('cardSidesHint').textContent=document.getElementById('sides').value==='single'?'단면: 상호·이름·연락처를 한 면에 배치합니다.':'양면: 브랜드 앞면과 정보 뒷면을 구분합니다.';document.querySelectorAll('[data-card-save]').forEach(b=>b.disabled=!template||fontBusy);document.getElementById('saveCardBack').disabled=!template||fontBusy||document.getElementById('sides').value!=='double';document.getElementById('saveCardFront').textContent=document.getElementById('sides').value==='single'?'단면 SVG 저장':'앞면 SVG 저장';}
  async function choose(index,move=true){
    const current=++generation;template='';selected=index;
    document.querySelectorAll('[data-card-sample]').forEach((button,i)=>button.setAttribute('aria-pressed',String(i===index)));
    document.getElementById('selectedSampleName').textContent=`선택한 견본: ${String(index+1).padStart(2,'0')} · ${labels[index]}`;
    status.textContent='견본을 작업창에 불러오고 있습니다…';
    document.querySelectorAll('[data-card-save]').forEach(b=>b.disabled=true);
    try{
      const response=await fetch(`/assets/business-card-templates/arkaon-${String(index+1).padStart(2,'0')}.svg`,{signal:AbortSignal.timeout(10000)});
      if(!response.ok)throw Error('load');const source=await response.text();if(current!==generation)return;
      template=source;for(const id of ['background','ink','accent'])document.getElementById(id).value=palettes[index][id];
      render();status.textContent=`${labels[index]} 견본을 적용했습니다. 입력 내용을 바꾸면 작업창에 바로 반영됩니다.`;
      render();
      if(move){const editor=document.getElementById('cardWorkspace');editor.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});document.getElementById('businessName').focus({preventScroll:true});}
    }catch{if(current===generation){status.textContent='견본을 불러오지 못했습니다. 다른 견본을 선택하거나 다시 시도해 주세요.';preview.srcdoc='<p>견본을 불러오지 못했습니다.</p>';}}
  }
  for(const item of APFCardFonts.presets){const option=document.createElement('option');option.value=item.id;option.textContent=item.name;fontSelect.append(option);}
  function dataUrl(bytes,format){let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));const mime={truetype:'ttf',opentype:'otf',woff:'woff',woff2:'woff2'}[format];return `data:font/${mime};base64,${btoa(binary)}`;}
  async function prepareFont(bytes,name,bundled=false,license=''){
    const format=APFCardFonts.inspect(bytes,name),face=new FontFace('APFCardPreview',bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength));
    await face.load();return {name,format,dataUrl:dataUrl(bytes,format),bundled,license,face};
  }
  function applyFont(font){
    activeFont=font?{name:font.name,format:font.format,dataUrl:font.dataUrl,bundled:font.bundled,license:font.license}:null;
    const sample=document.getElementById('cardFontSample');
    if(font){document.fonts.forEach(face=>{if(face.family==='APFCardPreview')document.fonts.delete(face);});document.fonts.add(font.face);sample.style.fontFamily='APFCardPreview, sans-serif';}else sample.style.fontFamily='"Noto Sans CJK KR",sans-serif';
    document.getElementById('cardFontName').textContent=font?`적용 중: ${font.name}`:'기본 고딕 사용 중';render();
  }
  fontSelect.addEventListener('change',async()=>{
    const current=++fontGeneration,key=fontSelect.value;
    fontBusy=true;render();fontStatus.textContent='서체를 불러오고 있습니다…';
    try{
      let font=null;
      if(key==='uploaded'){if(!uploadedFont)throw Error('글꼴을 먼저 업로드해 주세요.');font=uploadedFont;}
      else if(key!=='default'){
        const item=APFCardFonts.presets.find(item=>item.id===key);if(!item?.file)throw Error('서체를 다시 선택해 주세요.');
        if(!presetCache.has(key)){
          const response=await fetch(`/assets/card-fonts/${item.file}`,{signal:AbortSignal.timeout(20000)});if(!response.ok)throw Error('서체를 불러오지 못했습니다. 다시 선택해 주세요.');
          const licenseResponse=await fetch(`/assets/card-fonts/${item.file.replace('.woff2','-OFL.html')}`,{signal:AbortSignal.timeout(10000)});if(!licenseResponse.ok)throw Error('글꼴 라이선스를 불러오지 못했습니다. 다시 선택해 주세요.');
          const license=new DOMParser().parseFromString(await licenseResponse.text(),'text/html').body.textContent;
          presetCache.set(key,await prepareFont(new Uint8Array(await response.arrayBuffer()),item.file,true,license));
        }
        font=presetCache.get(key);
      }
      if(current!==fontGeneration)return;applyFont(font);fontStatus.textContent='서체를 적용했습니다. 미리보기에서 글자 배치를 확인해 주세요.';
    }catch(error){if(current===fontGeneration){fontSelect.value=activeFont?(activeFont.bundled?APFCardFonts.presets.find(item=>item.file===activeFont.name)?.id:'uploaded'):'default';fontStatus.textContent=error.message||'이 글꼴은 브라우저에서 읽을 수 없습니다.';}}
    finally{if(current===fontGeneration){fontBusy=false;render();}}
  });
  document.getElementById('cardFontUpload').addEventListener('change',async event=>{
    const file=event.target.files[0];if(!file)return;const current=++fontGeneration;fontBusy=true;render();fontStatus.textContent='업로드한 글꼴을 확인하고 있습니다…';
    try{
      if(file.size>APFCardFonts.maxBytes)throw Error('글꼴 파일은 10MB 이하로 선택해 주세요.');
      const font=await prepareFont(new Uint8Array(await file.arrayBuffer()),file.name);
      if(current!==fontGeneration)return;uploadedFont=font;
      let option=fontSelect.querySelector('[value="uploaded"]');if(!option){option=document.createElement('option');option.value='uploaded';fontSelect.append(option);}option.textContent=`내 글꼴 · ${file.name}`;fontSelect.value='uploaded';
      applyFont(font);document.getElementById('cardFontReset').hidden=false;fontStatus.textContent='내 글꼴을 적용했습니다. 명함과 함께 파일에 포함됩니다.';
    }catch(error){if(current===fontGeneration)fontStatus.textContent=error.message||'이 글꼴은 브라우저에서 읽을 수 없습니다. 다른 파일을 선택해 주세요.';}
    finally{event.target.value='';if(current===fontGeneration){fontBusy=false;render();}}
  });
  document.getElementById('cardFontReset').addEventListener('click',()=>{
    ++fontGeneration;fontBusy=false;uploadedFont=null;const active=fontSelect.value==='uploaded';fontSelect.querySelector('[value="uploaded"]')?.remove();document.getElementById('cardFontReset').hidden=true;
    if(active){fontSelect.value='default';applyFont(null);}fontStatus.textContent='업로드한 글꼴을 제거했습니다.';render();
  });
  let category='all',page=0;
  const pageSize=12;
  const categories={all:'전체',corporate:'기업·비즈니스',tech:'IT·테크',creative:'디자인·감성',service:'매장·서비스',premium:'프리미엄',portrait:'세로형'};
  function filter(reset=true){
    if(reset)page=0;
    const query=document.getElementById('cardSampleSearch').value.trim().toLowerCase();
    const matches=catalog.map((item,index)=>({item,index})).filter(({item})=>(category==='all'||item.category===category)&&`${item.id} ${item.name}`.toLowerCase().includes(query));
    const pages=Math.max(1,Math.ceil(matches.length/pageSize));page=Math.min(page,pages-1);
    const visible=new Set(matches.slice(page*pageSize,(page+1)*pageSize).map(({index})=>index));
    document.querySelectorAll('[data-card-sample]').forEach((button,index)=>{button.hidden=!visible.has(index);});
    document.getElementById('cardSampleCount').textContent=`전체 ${catalog.length}종 · 검색 결과 ${matches.length}종`;
    document.getElementById('cardPageLabel').textContent=`${page+1} / ${pages}`;
    document.getElementById('cardPagePrev').disabled=page===0;
    document.getElementById('cardPageNext').disabled=page===pages-1;
    document.getElementById('cardSampleEmpty').hidden=matches.length!==0;
  }
  for(const [id,delta] of [['cardPagePrev',-1],['cardPageNext',1]])document.getElementById(id).addEventListener('click',()=>{page+=delta;filter(false);document.getElementById('cardCollection').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});});
  Object.entries(categories).forEach(([key,label])=>{const button=document.createElement('button');button.type='button';button.textContent=label;button.setAttribute('aria-pressed',String(key==='all'));button.addEventListener('click',()=>{category=key;document.querySelectorAll('#cardSampleCategories button').forEach(item=>item.setAttribute('aria-pressed',String(item===button)));filter();});document.getElementById('cardSampleCategories').append(button);});
  document.getElementById('cardSampleSearch').addEventListener('input',filter);
  labels.forEach((label,index)=>{
    const button=document.createElement('button');button.type='button';button.dataset.cardSample=index;button.setAttribute('aria-pressed','false');
    const image=document.createElement('img');image.src=`/assets/business-card-templates/arkaon-${String(index+1).padStart(2,'0')}.svg`;image.alt='';image.width=1200;image.height=800;image.loading='lazy';
    const title=document.createElement('span');title.textContent=`${String(index+1).padStart(2,'0')} · ${label}`;const hint=document.createElement('small');hint.className='studio-card-hint';hint.textContent='이 디자인으로 시작 →';button.append(image,title,hint);button.addEventListener('click',()=>choose(index));grid.append(button);
  });
  fields.forEach(id=>document.getElementById(id).addEventListener('input',render));
  document.getElementById('form').addEventListener('submit',event=>{
    event.preventDefault();if(!template)return;
    if(fontBusy)return;
    const input=values(),html=APFCardTemplate.documentHtml(svg());
    APFHomeServices.downloadText(`arkaon-business-card-${input.sides}.html`,html);
    try{APFHomeServices.saveProject({type:'logo-card',title:input.businessName,html,cardSample:selected+1,cardValues:{...input,cardFont:activeFont?{name:activeFont.name}:null}});status.textContent='수정한 명함을 내 작업에 저장하고 글꼴이 포함된 HTML 파일로 내려받았습니다.';}
    catch{status.textContent='HTML 파일을 내려받았습니다. 브라우저 저장 공간이 부족해 내 작업에는 저장하지 못했습니다.';}

  });
  document.getElementById('saveCardSvg').addEventListener('click',()=>{if(template&&!fontBusy)APFHomeServices.downloadText('arkaon-business-card.svg',svg(),'image/svg+xml;charset=utf-8');});
  for(const [id,side] of [['saveCardFront','front'],['saveCardBack','back']])document.getElementById(id).addEventListener('click',()=>{if(template&&!fontBusy&&document.getElementById('form').reportValidity()){const face=APFCardTemplate.faceSvg(svg(),side);if(face)APFHomeServices.downloadText(`arkaon-card-${side}.svg`,face,'image/svg+xml;charset=utf-8');}});
  filter();
  choose(0,false);
})();
