/* Simple site entry and Foundry data authorization remain separate. */
(() => {
  const content=document.getElementById('operatorProtected');
  const gate=document.getElementById('operatorGate');
  const status=document.getElementById('operatorGateStatus');
  const login=document.getElementById('operatorLogin');
  const form=document.getElementById('operatorPasswordForm');
  const password=document.getElementById('operatorPassword');
  const logout=document.getElementById('operatorLogout');
  const base=APFHomeServices.getApiBase();
  const lock=message=>{content.hidden=true;gate.hidden=false;logout.hidden=true;status.textContent=message;
    const report=document.getElementById('mailboxReport');if(report)report.value='';
    document.getElementById('mailboxItems')?.replaceChildren();
  };
  if(base){login.href=`${base}/console/login`;login.textContent='Foundry 데이터 인증';login.hidden=false;}
  form.hidden=false;
  async function check(){
    try{
      const endpoint='/api/operator-session';
      const response=await fetch(endpoint,{credentials:'include',redirect:'error',cache:'no-store',signal:AbortSignal.timeout(10000)});
      if(response.status!==204){lock(response.status===503?'Netlify에 관리자 비밀번호를 한 번 설정해 주세요.':'관리자 비밀번호를 입력해 주세요.');return;}
      gate.hidden=true;content.hidden=false;logout.hidden=false;
      if(!base){const hint=document.getElementById('consoleHint');if(hint)hint.textContent='간편 관리자 모드입니다. 실제 운영 콘솔·제안 데이터 조회는 Foundry 서버 연결 후 사용할 수 있습니다.';}
    }catch{lock('인증 서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.');}
  }
  form.addEventListener('submit',async e=>{
    e.preventDefault();const button=form.querySelector('button');button.disabled=true;
    try{const response=await fetch('/api/operator-session',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:password.value})});password.value='';
      if(response.ok)await check();else lock(response.status===429?'입력 시도가 많습니다. 1분 후 다시 시도해 주세요.':response.status===503?'Netlify에 관리자 비밀번호를 한 번 설정해 주세요.':'비밀번호를 확인해 주세요.');
    }catch{lock('서버 연결을 확인해 주세요.');}finally{button.disabled=false;}
  });
  logout.addEventListener('click',async()=>{try{const response=await fetch('/api/operator-session',{method:'DELETE',credentials:'same-origin'});lock(response.ok?'로그아웃했습니다.':'로그아웃 확인에 실패했습니다. 다시 시도해 주세요.');}catch{lock('서버 연결을 확인해 주세요.');}});
  document.getElementById('operatorRecheck').addEventListener('click',check);
  window.addEventListener('focus',check);
  window.addEventListener('pagehide',()=>lock('인증을 다시 확인해 주세요.'));
  document.addEventListener('visibilitychange',()=>{if(document.hidden)lock('인증을 다시 확인해 주세요.');else check();});
  setInterval(check,60000);check();
})();
