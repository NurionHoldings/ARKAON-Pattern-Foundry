(() => {
  const catalog=APFCardCatalog;
  const labels=catalog.map(item=>item.name);
  const palettes=catalog.map(item=>item.palette);
  const fields=['businessName','personName','role','tagline','website','address','addressDetail','email','phone','sides','background','ink','accent'];
  const grid=document.getElementById('cardSampleGrid'),status=document.getElementById('cardEditorStatus'),preview=document.getElementById('preview');
  let selected=0,template='',generation=0;
  const values=()=>Object.fromEntries(fields.map(id=>[id,document.getElementById(id).value]));
  const svg=()=>APFCardTemplate.compose(template,values(),palettes[selected]);
  function render(){if(template)preview.srcdoc=APFCardTemplate.documentHtml(svg());document.getElementById('cardSidesHint').textContent=document.getElementById('sides').value==='single'?'단면: 상호·이름·연락처를 한 면에 배치합니다.':'양면: 브랜드 앞면과 정보 뒷면을 구분합니다.';document.getElementById('saveCardBack').disabled=!template||document.getElementById('sides').value!=='double';document.getElementById('saveCardFront').textContent=document.getElementById('sides').value==='single'?'단면 SVG 저장':'앞면 SVG 저장';}
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
      document.querySelectorAll('[data-card-save]').forEach(b=>b.disabled=false);render();
      if(move){const editor=document.getElementById('cardWorkspace');editor.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});document.getElementById('businessName').focus({preventScroll:true});}
    }catch{if(current===generation){status.textContent='견본을 불러오지 못했습니다. 다른 견본을 선택하거나 다시 시도해 주세요.';preview.srcdoc='<p>견본을 불러오지 못했습니다.</p>';}}
  }
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
    try{const input=values(),html=APFCardTemplate.documentHtml(svg());APFHomeServices.saveProject({type:'logo-card',title:input.businessName,html,cardSample:selected+1,cardValues:input});APFHomeServices.downloadText(`arkaon-business-card-${input.sides}.html`,html);status.textContent='수정한 명함을 내 작업에 저장하고 HTML 파일로 내려받았습니다.';}
    catch{status.textContent='저장에 실패했습니다. 브라우저 저장 공간을 확인한 뒤 다시 시도해 주세요.';}
  });
  document.getElementById('saveCardSvg').addEventListener('click',()=>{if(template)APFHomeServices.downloadText('arkaon-business-card.svg',svg(),'image/svg+xml;charset=utf-8');});
  for(const [id,side] of [['saveCardFront','front'],['saveCardBack','back']])document.getElementById(id).addEventListener('click',()=>{if(template&&document.getElementById('form').reportValidity()){const face=APFCardTemplate.faceSvg(svg(),side);if(face)APFHomeServices.downloadText(`arkaon-card-${side}.svg`,face,'image/svg+xml;charset=utf-8');}});
  filter();
  choose(0,false);
})();
