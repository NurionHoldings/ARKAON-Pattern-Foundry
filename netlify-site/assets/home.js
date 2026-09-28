async function connectInspection(){
  const status=document.getElementById('inspection-state');
  const link=document.getElementById('inspection-link');
  try{
    const response=await fetch('/api-config.json',{cache:'no-store'});
    if(!response.ok)throw new Error('config unavailable');
    const config=await response.json();
    if(config.inspection_available===true){
      link.hidden=false;
      status.textContent='시안 미리보기를 이용할 수 있습니다. 출력·다운로드는 계정과 결제 후 진행됩니다.';
    }else status.textContent='제작 체험 연결을 준비 중입니다. 현재는 제작 과정과 구성 예시를 확인할 수 있습니다.';
  }catch(_error){status.textContent='제작 체험 상태를 확인할 수 없습니다. 잠시 후 다시 확인해 주세요.';}
}
connectInspection();
