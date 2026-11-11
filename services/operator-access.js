/* Presentation gate; Foundry independently authorizes every protected request. */
(() => {
  const content=document.getElementById('operatorProtected');
  const gate=document.getElementById('operatorGate');
  const status=document.getElementById('operatorGateStatus');
  const login=document.getElementById('operatorLogin');
  const base=APFHomeServices.getApiBase();
  const lock=message=>{content.hidden=true;gate.hidden=false;status.textContent=message;
    const report=document.getElementById('mailboxReport');if(report)report.value='';
    document.getElementById('mailboxItems')?.replaceChildren();
  };
  if(!base){lock('Foundry 서버 연결이 필요합니다. 계정 화면에서 운영 서버 주소를 설정해 주세요.');login.hidden=true;return;}
  login.href=`${base}/console/login`;login.hidden=false;
  async function check(){
    try{
      const response=await fetch(`${base}/v1/console/access`,{credentials:'include',redirect:'error',cache:'no-store',signal:AbortSignal.timeout(10000)});
      if(response.status!==204){lock('운영자 로그인이 필요하거나 접근 권한이 없습니다.');return;}
      gate.hidden=true;content.hidden=false;
    }catch{lock('운영자 인증을 확인할 수 없어 접근을 잠갔습니다. 서버 연결을 확인해 주세요.');}
  }
  document.getElementById('operatorRecheck').addEventListener('click',check);
  window.addEventListener('focus',check);
  window.addEventListener('pagehide',()=>lock('운영자 인증을 다시 확인해 주세요.'));
  document.addEventListener('visibilitychange',()=>{if(document.hidden)lock('운영자 인증을 다시 확인해 주세요.');else check();});
  setInterval(check,60000);check();
})();
