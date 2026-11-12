(() => {
  const labels=['기업 기본형','블랙 골드','청록 브랜드','화이트 미니멀','타이포그래피','코발트 테크','세로 포인트','버건디 클래식','오렌지 액센트','라벤더 스튜디오','내추럴 페이퍼','모노그램 프리미엄','센터 심벌','사이드 밴드','상단 리본','에디토리얼','테크 그리드','소프트 아치','건축 라인','시그니처','세로 화이트','세로 다크','볼드 하프','넘버 인덱스'];
  const palettes=[['#ffffff','#203c55','#2686a4'],['#171b23','#f1dfb9','#bd9551'],['#194e4a','#fff9eb','#c5b27d'],['#faf8f1','#222b31','#697d80'],['#e5e8ed','#192534','#4774aa'],['#16366a','#ffffff','#68d9f0'],['#ffffff','#293b43','#399899'],['#542e3b','#f7eede','#c1a57e'],['#fffaf3','#34312c','#e78335'],['#e6dcef','#423554','#8a6eab'],['#e8dfcd','#434b39','#839174'],['#eeeae2','#20282b','#8b806e'],['#f7f8fa','#22324a','#536cb7'],['#ffffff','#273b39','#246f61'],['#fff9ee','#493c2f','#c47540'],['#eee9df','#2d302c','#8d7160'],['#101d31','#edf5ff','#73aeda'],['#e3e9e2','#314c40','#7c9b87'],['#f5f5f2','#27313a','#9b8863'],['#fffaf6','#5b3944','#a86c7d'],['#ffffff','#273747','#4685a4'],['#1d2928','#f2eee4','#c8af7b'],['#233c53','#ffffff','#9fc5cb'],['#f2eee5','#252f30','#b16a48']].map(([background,ink,accent])=>({background,ink,accent}));
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
      if(move){const editor=document.getElementById('form');editor.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});document.getElementById('businessName').focus({preventScroll:true});}
    }catch{if(current===generation){status.textContent='견본을 불러오지 못했습니다. 다른 견본을 선택하거나 다시 시도해 주세요.';preview.srcdoc='<p>견본을 불러오지 못했습니다.</p>';}}
  }
  labels.forEach((label,index)=>{
    const button=document.createElement('button');button.type='button';button.dataset.cardSample=index;button.setAttribute('aria-pressed','false');
    const image=document.createElement('img');image.src=`/assets/business-card-templates/arkaon-${String(index+1).padStart(2,'0')}.svg`;image.alt='';image.width=1200;image.height=800;image.loading='lazy';
    const title=document.createElement('span');title.textContent=`${String(index+1).padStart(2,'0')} · ${label}`;button.append(image,title);button.addEventListener('click',()=>choose(index));grid.append(button);
  });
  fields.forEach(id=>document.getElementById(id).addEventListener('input',render));
  document.getElementById('form').addEventListener('submit',event=>{
    event.preventDefault();if(!template)return;
    try{const input=values(),html=APFCardTemplate.documentHtml(svg());APFHomeServices.saveProject({type:'logo-card',title:input.businessName,html,cardSample:selected+1,cardValues:input});APFHomeServices.downloadText(`arkaon-business-card-${input.sides}.html`,html);status.textContent='수정한 명함을 내 작업에 저장하고 HTML 파일로 내려받았습니다.';}
    catch{status.textContent='저장에 실패했습니다. 브라우저 저장 공간을 확인한 뒤 다시 시도해 주세요.';}
  });
  document.getElementById('saveCardSvg').addEventListener('click',()=>{if(template)APFHomeServices.downloadText('arkaon-business-card.svg',svg(),'image/svg+xml;charset=utf-8');});
  for(const [id,side] of [['saveCardFront','front'],['saveCardBack','back']])document.getElementById(id).addEventListener('click',()=>{if(template&&document.getElementById('form').reportValidity()){const face=APFCardTemplate.faceSvg(svg(),side);if(face)APFHomeServices.downloadText(`arkaon-card-${side}.svg`,face,'image/svg+xml;charset=utf-8');}});
  choose(0,false);
})();
