/* Original rule-based renderer; it does not call or train an AI model. */
(() => {
  'use strict';
  const escape = value => String(value || '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const lines=value=>String(value||'').split('\n').map(s=>s.trim()).filter(Boolean).slice(0,8);
  const packs={
    service:{label:'전문 서비스',offer:'어떤 도움을 드리나요',action:'상담 안내 확인',process:'함께 진행하는 방법',slots:['대표 서비스 입력 필요','관련 서비스 입력 필요','추가 서비스 입력 필요'],details:['해결하는 문제와 제공 범위를 설명해 주세요.','고객이 받는 결과물과 진행 방식을 적어 주세요.','준비할 내용과 제외되는 범위를 설명해 주세요.'],questions:['어떤 요청을 상담할 수 있나요?','비용과 일정은 어떻게 정하나요?','시작하려면 무엇을 준비하나요?'],answers:['입력된 서비스 범위에 맞는지 먼저 확인해 주세요.','실제 요청 범위를 확인한 후 견적과 일정을 협의해야 합니다.','목적과 원하는 결과, 참고자료를 준비해 주세요.']},
    shop:{label:'가게와 브랜드',offer:'우리 가게에서 만나는 것',action:'방문 안내 확인',process:'방문·구매 전 확인',slots:['대표 상품 입력 필요','추천 상품 입력 필요','추가 상품 입력 필요'],details:['상품의 특징과 구성을 설명해 주세요.','소재·맛·사용 방법 등 선택에 필요한 정보를 적어 주세요.','실제 가격과 재고, 주문 가능 여부를 확인해 주세요.'],questions:['상품은 어떻게 고르나요?','방문·주문은 어떻게 하나요?','가격과 이용시간은 어디서 확인하나요?'],answers:['상품별 특징을 비교하고 용도에 맞는 구성을 확인해 주세요.','주소와 주문 방법은 아래 연락 안내를 확인해 주세요.','확인된 가격·운영시간이 아직 없습니다. 공개 전에 실제 정보를 채워 주세요.']},
    portfolio:{label:'개인 포트폴리오',offer:'소개하고 싶은 작업',action:'협업 안내 확인',process:'협업을 시작하는 순서',slots:['대표 작업 입력 필요','관련 프로젝트 입력 필요','다른 작업 입력 필요'],details:['작업 목적과 본인이 맡은 역할을 설명해 주세요.','문제를 해결한 방식과 결과를 근거와 함께 적어 주세요.','사용 기술·진행 기간·공개 가능한 자료를 확인해 주세요.'],questions:['어떤 분야에서 협업할 수 있나요?','작업 사례를 더 볼 수 있나요?','협업 요청에는 무엇을 담나요?'],answers:['소개한 역량에 맞는 협업 범위를 먼저 확인해 주세요.','공개 가능한 작업 링크와 이미지 추가가 필요합니다.','목적과 범위, 희망 일정과 연락 방법을 전달해 주세요.']}
  };
  function compose(raw){
    const industry=Object.hasOwn(packs,raw.industry)?raw.industry:'service';
    const needs=[];const labels={title:'이름',audience:'대상 고객',story:'소개',offerings:'대표 항목',difference:'차별점',process:'이용 과정',contact:'연락 안내'};
    Object.entries(labels).forEach(([k,v])=>{if(!String(raw[k]||'').trim())needs.push(v);});
    const offerings=(lines(raw.offerings).length?lines(raw.offerings):packs[industry].slots).map((line,i)=>{
      const split=line.indexOf('|');
      const title=(split<0?line:line.slice(0,split)).trim();
      const detail=split<0?'':line.slice(split+1).trim();
      if(!detail)needs.push(`대표 항목 ${i+1} 상세 설명`);
      return {title:title||'항목 이름 입력 필요',detail:detail||packs[industry].details[i%3],needs_detail:!detail};
    });
    return {industry,pack:packs[industry],needs,offerings,theme:['editorial','night','minimal'].includes(raw.theme)?raw.theme:'editorial',
      title:String(raw.title||'').trim()||'당신의 브랜드',audience:String(raw.audience||'').trim()||'대상 고객을 입력해 주세요',
      story:String(raw.story||'').trim()||'하는 일과 누구에게 도움이 되는지 당신의 이야기를 적어 주세요.',
      difference:String(raw.difference||'').trim()||'실제로 설명할 수 있는 강점과 차별점을 입력해 주세요.',
      contact:String(raw.contact||'').trim()||'연락처·주소·이용시간을 확인 후 입력해 주세요.',
      process:lines(raw.process).length?lines(raw.process):['요청과 목적 확인 필요','범위·일정 안내 필요','결과 확인 방식 입력 필요'],sample:raw.sample===true};
  }
  function render(raw){const b=compose(raw),p=b.pack;
    const cards=b.offerings.map((x,i)=>`<article class="offer"><span>0${i+1}${x.needs_detail?' · 설명 입력 필요':''}</span><h3>${escape(x.title)}</h3><p>${escape(x.detail)}</p></article>`).join('');
    return `<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escape(b.title)}</title><style>
    *{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,sans-serif;line-height:1.8;background:var(--bg);color:var(--ink);--bg:#f5f0e6;--ink:#243c2d;--muted:#52664f;--panel:#e4e9d8;--line:#c5cfbb;--accent:#34533b}.wrap{max-width:1160px;margin:auto;padding:0 6%}a{color:inherit;text-decoration:none}:focus-visible{outline:3px solid currentColor;outline-offset:4px}.draft{font-size:11px;background:var(--ink);color:var(--bg);padding:8px 6%}.nav{padding:22px 0;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:20px;font-size:11px}.nav strong{font-size:17px}.links{display:flex;gap:20px}.hero{display:grid;grid-template-columns:1.2fr .8fr;align-items:center;gap:8%;padding:65px 0}.eyebrow{font-size:10px;letter-spacing:.14em;color:var(--muted)}h1{font-size:clamp(35px,5vw,65px);letter-spacing:-.065em;line-height:1.2;margin:20px 0;overflow-wrap:anywhere}h2{font-size:clamp(25px,3vw,36px);line-height:1.35;letter-spacing:-.05em;margin:0 0 20px}h3{font-size:20px;line-height:1.4;letter-spacing:-.04em}p{font-size:13px;color:var(--muted);white-space:pre-line;overflow-wrap:anywhere}.cta{display:inline-block;background:var(--accent);color:white;padding:12px 22px;font-size:12px;border-radius:5px;margin-top:16px}.visual{aspect-ratio:4/5;border-radius:140px 140px 10px 10px;background:var(--panel);position:relative;overflow:hidden;display:flex;flex-direction:column;justify-content:end;padding:30px}.visual:before{content:'';position:absolute;width:155px;height:155px;left:20%;top:15%;border:25px solid var(--accent);border-radius:50%;opacity:.25}.visual:after{content:'';position:absolute;width:130%;height:80px;left:-10%;top:55%;transform:rotate(-30deg);background:var(--accent);opacity:.12}.visual b{font-family:Georgia,serif;font-size:65px;line-height:1;z-index:1}.visual small{font-size:10px;letter-spacing:.12em;margin-top:16px}.section{padding:48px 0;border-top:1px solid var(--line)}.offers{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.offer{padding:24px 20px;background:var(--panel);border-radius:8px}.offer span{font-size:11px;color:var(--muted)}.offer p{font-size:12px}.about{display:grid;grid-template-columns:1fr 1fr;gap:8%}.process{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px}.process li{border-top:2px solid var(--line);padding-top:18px}.process span{font-size:11px}details{border-bottom:1px solid var(--line);padding:18px 0;font-size:13px}summary{cursor:pointer}.contact{background:var(--panel);padding:32px;border-radius:10px}small{color:var(--muted);font-size:10px}footer{padding:25px 0 35px;font-size:10px;color:var(--muted)}.night{--bg:#132334;--ink:#edf5ee;--muted:#b2c9c4;--panel:#21394a;--line:#3d5664;--accent:#315e54}.night .hero{grid-template-columns:1fr;text-align:center;padding:65px 5%}.night .visual{aspect-ratio:auto;height:150px;border-radius:10px;text-align:left}.night .visual:before{left:65%;top:-25%}.night .visual b{font-size:45px}.night .offers{grid-template-columns:1fr}.night .offer{display:grid;grid-template-columns:35px 1fr 1fr;gap:15px;align-items:center}.minimal{--bg:#fff;--ink:#20343a;--muted:#526870;--panel:#f1f5f5;--line:#d1dedf;--accent:#264b5b}.minimal .hero{grid-template-columns:1fr}.minimal .visual{display:none}.minimal .offer{background:none;border:1px solid var(--line);border-radius:0}.minimal .contact{border-radius:0}@media(max-width:650px){.wrap{padding:0 7%}.hero{grid-template-columns:1fr;gap:25px;padding:38px 0}h1{font-size:39px}.visual{aspect-ratio:2/1;border-radius:80px 80px 8px 8px}.visual b{font-size:42px}.visual:before{width:110px;height:110px;top:-20%;left:60%}.offers,.process,.about{grid-template-columns:1fr}.section{padding:34px 0}.night .offer{display:block}.night .hero{padding:38px 0}.links{gap:12px}.contact{padding:23px}}
    </style></head><body class="${b.theme}"><div class="draft">${b.sample?'가상 예시 · 실제 사업 정보가 아닙니다':'작성 중인 초안'} · 확인 필요 ${b.needs.length}개 · 아직 공개되지 않았습니다</div><div class="wrap"><nav class="nav"><strong>${escape(b.title)}</strong><div class="links"><a href="#offer">${b.industry==='portfolio'?'작업':'서비스'}</a><a href="#about">소개</a><a href="#contact">연락 안내</a></div></nav><main><section class="hero"><div><span class="eyebrow">${escape(p.label)} / YOUR NEXT CHAPTER</span><h1>${escape(b.title)}<br>당신의 이야기를<br>만나는 곳.</h1><p>${escape(b.audience)}</p><p>${escape(b.story)}</p><a class="cta" href="#contact">${escape(p.action)} ↗</a></div><div class="visual" aria-hidden="true"><b>${escape(b.title.slice(0,2))}.</b><small>IDEAS, MADE TANGIBLE.</small></div></section><section class="section" id="offer"><h2>${escape(p.offer)}</h2><p>상세 설명은 작성 가이드입니다. 실제 내용으로 다듬어 주세요.</p><div class="offers">${cards}</div></section><section class="section about" id="about"><h2>우리가 중요하게<br>생각하는 것.</h2><p>${escape(b.difference)}</p></section><section class="section"><h2>${escape(p.process)}</h2><ol class="process">${b.process.map((s,i)=>`<li><span>0${i+1}</span><p>${escape(s)}</p></li>`).join('')}</ol></section><section class="section"><h2>궁금한 점을 먼저.</h2><p>공개 전 실제 운영 기준으로 확인해 주세요.</p>${p.questions.map((q,i)=>`<details><summary>${escape(q)}</summary><p>${escape(p.answers[i])}</p></details>`).join('')}</section><section class="section" id="contact"><div class="contact"><h2>다음 이야기를<br>함께 시작해요.</h2><p>${escape(b.contact)}</p><small>상담·예약 접수 기능은 연결되지 않았습니다.</small></div></section></main><footer>${escape(b.title)} · ARKAON 초안 · 작성 가이드와 실제 정보 확인 필요</footer></div></body></html>`;
  }
  if(typeof module!=='undefined'&&module.exports)module.exports={compose,render};
  if(typeof window==='undefined')return;
  window.APFStudio={compose,render};
  if(!document.getElementById('brief'))return;
  const params=new URLSearchParams(location.search);
  const linkSession=params.get('session')||'';
  const linkProposal=params.get('proposal')||'';
  let linkConsentId=params.get('reference_consent_request_id')||'';
  let activeProjectId=params.get('project')||null;
  let theme='editorial',step=0,sample=false,previewUrl=null;
  const fields=['industry','title','audience','story','offerings','difference','process','contact'];
  const values=()=>({...Object.fromEntries(fields.map(id=>[id,document.getElementById(id).value])),theme,sample});
  function applyBrief(brief){
    if(!brief)return;
    if(brief.industry)document.getElementById('industry').value=brief.industry;
    fields.forEach(id=>{if(brief[id]!=null)document.getElementById(id).value=String(brief[id]);});
    if(brief.theme&&['editorial','night','minimal'].includes(brief.theme)){theme=brief.theme;document.querySelectorAll('[data-theme]').forEach(t=>t.setAttribute('aria-pressed',String(t.dataset.theme===theme)));}
    sample=false;
  }
  async function loadLinkedDraft(){
    const msg=document.getElementById('message');
    const stash=window.APFHomeServices.popReferenceConsentStash?.();
    if(stash){
      if(stash.project_id&&!activeProjectId)activeProjectId=stash.project_id;
      let briefFromStash=stash.brief;
      if(!briefFromStash&&stash.title&&stash.message){
        briefFromStash=window.APFHomeServices.buildStudioBriefFromWorkRequest?.({title:stash.title,message:stash.message,scope:stash.scope||'LANDING'});
      }
      if(briefFromStash){
        applyBrief(briefFromStash);
        const sid=stash.session_id||linkSession;
        if(sid)window.APFHomeServices.saveCoCreationStudioDraft?.(sid,{brief:briefFromStash,proposal_id:stash.proposal_id||linkProposal,project_id:activeProjectId,reference_consent_request_id:stash.reference_consent_request_id||linkConsentId||null});
        if(stash.reference_consent_request_id)linkConsentId=stash.reference_consent_request_id;
      }
    }
    if(activeProjectId){
      const item=window.APFHomeServices.readProjects().find(p=>p.id===activeProjectId);
      if(item?.brief)applyBrief(item.brief);
    }
    const sessionForLoad=linkSession||stash?.session_id||(params.get('session')||'');
    if(sessionForLoad){
      const local=window.APFHomeServices.loadCoCreationStudioDraft?.(sessionForLoad);
      if(local?.brief)applyBrief(local.brief);
      if(local?.project_id)activeProjectId=local.project_id;
      try{
        const remote=await window.APFHomeServices.fetchCoCreationStudioDraft?.(sessionForLoad);
        if(remote?.brief){
          applyBrief(remote.brief);
          if(remote.local_project_id)activeProjectId=remote.local_project_id;
          if(remote.reference_consent_request_id)linkConsentId=remote.reference_consent_request_id;
          window.APFHomeServices.saveCoCreationStudioDraft?.(sessionForLoad,{brief:remote.brief,proposal_id:remote.proposal_id,project_id:activeProjectId,reference_consent_request_id:remote.reference_consent_request_id||linkConsentId||null});
        }
      }catch{
        if(msg)msg.textContent='서버 초안을 불러오지 못했습니다. 이 브라우저에 저장된 내용을 사용합니다.';
      }
    }
  }
  function update(){const b=compose(values());if(previewUrl)URL.revokeObjectURL(previewUrl);previewUrl=URL.createObjectURL(new Blob([render(values())],{type:'text/html;charset=utf-8'}));document.getElementById('preview').src=previewUrl;const list=document.getElementById('missing');list.replaceChildren();(b.needs.length?b.needs.map(x=>`${x}: 입력 필요`):['기본 입력 완료 · 실제 내용 확인 필요']).forEach(text=>{const li=document.createElement('li');li.textContent=text;list.append(li);});}
  function go(n){step=n;document.querySelectorAll('[data-panel]').forEach(x=>x.hidden=Number(x.dataset.panel)!==step);document.querySelectorAll('[data-step]').forEach(x=>{if(Number(x.dataset.step)===step)x.setAttribute('aria-current','step');else x.removeAttribute('aria-current');});document.getElementById('next').hidden=step===2;document.getElementById('save').hidden=step!==2;document.getElementById('next').textContent=step===0?'분위기 고르기 →':'내용 다듬기 →';}
  fields.forEach(id=>document.getElementById(id).addEventListener('input',update));
  document.querySelectorAll('[data-step]').forEach(x=>x.addEventListener('click',()=>go(Number(x.dataset.step))));
  document.querySelectorAll('[data-theme]').forEach(x=>x.addEventListener('click',()=>{theme=x.dataset.theme;document.querySelectorAll('[data-theme]').forEach(t=>t.setAttribute('aria-pressed',String(t===x)));update();}));
  document.getElementById('next').addEventListener('click',()=>{go(Math.min(step+1,2));document.querySelector(`[data-panel="${step}"]`).querySelector('input,button,textarea')?.focus();});
  document.getElementById('example').addEventListener('click',()=>{const v={industry:'service',title:'온유 스튜디오',audience:'브랜드를 처음 시작하는 작은 가게를 위해',story:'복잡한 생각을 정리하고 가게의 이야기를 전달하는 디자인을 함께 만듭니다.',offerings:'브랜드 방향 정리\n시각 디자인\n소개 홈페이지',difference:'이해하기 쉬운 설명과 작은 화면에서도 읽기 편한 구성을 중요하게 생각합니다.',process:'목적과 고민 나누기\n구성과 디자인 방향 확인\n초안을 보고 함께 다듬기',contact:''};fields.forEach(id=>document.getElementById(id).value=v[id]);sample=true;update();});
  ['desktop','mobile'].forEach(id=>document.getElementById(id).addEventListener('click',()=>{document.querySelector('.frame').classList.toggle('phone',id==='mobile');['desktop','mobile'].forEach(k=>document.getElementById(k).setAttribute('aria-pressed',String(k===id)));}));
  document.getElementById('brief').addEventListener('submit',async e=>{
    e.preventDefault();
    const msgEl=document.getElementById('message');
    const v=values();
    if(!v.title.trim()){go(0);document.getElementById('title').focus();msgEl.textContent='이름을 입력해 주세요.';return;}
    let saved;
    try{
      const html=render(v);
      const sessionForSave=linkSession||params.get('session')||null;
      const proposalForSave=linkProposal||params.get('proposal')||null;
      const consentForSave=linkConsentId||params.get('reference_consent_request_id')||null;
      saved=window.APFHomeServices.saveProject({id:activeProjectId||undefined,type:'site',title:v.title,html,brief:v,creation_mode:'rule_based_studio',publish_ready:false,co_creation_session_id:sessionForSave,co_creation_proposal_id:proposalForSave,reference_consent_request_id:consentForSave});
      activeProjectId=saved.id;
    }catch{
      msgEl.textContent='저장하지 못했습니다. 브라우저 저장 공간·권한을 확인해 주세요.';
      return;
    }
    const sessionForSave=linkSession||params.get('session')||null;
    const proposalForSave=linkProposal||params.get('proposal')||null;
    const consentForSave=linkConsentId||params.get('reference_consent_request_id')||null;
    if(sessionForSave){
      window.APFHomeServices.saveCoCreationStudioDraft(sessionForSave,{brief:v,proposal_id:proposalForSave,project_id:saved.id,reference_consent_request_id:consentForSave});
    }
    let syncNote='초안을 저장했습니다. 이 브라우저에서 다시 열면 내용이 유지됩니다.';
    if(sessionForSave&&proposalForSave&&window.APFHomeServices.canConsoleApiSync?.()){
      try{
        const put=await window.APFHomeServices.consoleApiFetch(`/v1/console/co-creation/studio/${encodeURIComponent(sessionForSave)}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({proposal_id:proposalForSave,brief:v,local_project_id:saved.id,reference_consent_request_id:consentForSave})});
        if(!put.ok){
          const detail=await put.json().catch(()=>({}));
          syncNote=`브라우저에는 저장됐지만 서버 동기화 실패 (${put.status}${detail.detail?`: ${detail.detail}`:''}). API와 같은 도메인에서 로그인했는지 확인해 주세요.`;
        }else syncNote='초안을 저장했습니다. 브라우저와 서버 초안이 갱신됐습니다.';
      }catch(err){
        syncNote=err?.message==='CSRF_TOKEN_MISSING'||err?.message==='API_CROSS_ORIGIN'
          ? '브라우저에 저장됐습니다. API가 다른 사이트면 서버 동기화는 API 도메인에서 로그인·설정 후 가능합니다.'
          : '브라우저에 저장됐습니다. 서버 동기화는 나중에 다시 시도할 수 있습니다.';
      }
    }else if(sessionForSave&&proposalForSave&&window.APFHomeServices.getApiBase?.()){
      syncNote='브라우저에 저장됐습니다. API 주소가 다른 사이트면 CSRF 쿠키를 공유할 수 없어 서버 동기화를 건너뜁니다.';
    }
    msgEl.textContent=syncNote;
    const q=new URLSearchParams(location.search);
    q.set('project',saved.id);
    if(sessionForSave)q.set('session',sessionForSave);
    if(proposalForSave)q.set('proposal',proposalForSave);
    if(consentForSave)q.set('reference_consent_request_id',consentForSave);
    history.replaceState(null,'',`${location.pathname}?${q}`);
  });
  loadLinkedDraft().then(()=>update()).catch(()=>update());
})();
