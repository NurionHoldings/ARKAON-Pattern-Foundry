import { randomUUID } from 'node:crypto';
const headers={'Cache-Control':'no-store','Content-Type':'application/json; charset=utf-8','X-Content-Type-Options':'nosniff'};
const reply=(status,body)=>new Response(JSON.stringify(body),{status,headers});

/* Immutable review documents only: no account balances, approvals or code execution. */
export function createOperationsHandler({authorize,openStore}) {
  return async request=>{
    const url=new URL(request.url);
    if(!['/api/operations/health','/api/operations/mailbox'].includes(url.pathname))return reply(404,{message:'없는 API입니다.'});
    if(!url.pathname.endsWith('/health')){
      const auth=await authorize(request);
      if(auth.status!==204)return reply(auth.status,{message:auth.status===503?'관리자 비밀번호 설정이 필요합니다.':'관리자 인증이 필요합니다.'});
    }
    if(!['GET','POST'].includes(request.method))return reply(405,{message:'허용되지 않은 요청입니다.'});
    if(request.method==='POST'&&request.headers.get('origin')!==url.origin)return reply(403,{message:'같은 사이트에서만 등록할 수 있습니다.'});
    try {
      const store=openStore();
      if(url.pathname.endsWith('/health')){
        if(request.method!=='GET')return reply(405,{message:'조회만 가능합니다.'});
        await store.get('health-probe',{type:'json'});
        return reply(200,{status:'ok',storage:'connected',mode:'review-only',capabilities:['mailbox.create','mailbox.read'],foundry_connected:false});
      }
      if(request.method==='GET'){
        const {blobs}=await store.list({prefix:'reports/'});
        const keys=blobs.map(x=>x.key).sort();
        const items=(await Promise.all(keys.slice(0,100).map(key=>store.get(key,{type:'json'})))).filter(Boolean);
        return reply(200,{items,total:keys.length,limit:100,truncated:keys.length>100});
      }
      if(!request.headers.get('content-type')?.startsWith('application/json'))return reply(415,{message:'JSON 요청이 필요합니다.'});
      const reader=request.body?.getReader();let size=0;const chunks=[];
      if(!reader)return reply(400,{message:'내용이 필요합니다.'});
      while(true){const {value,done}=await reader.read();if(done)break;size+=value.byteLength;if(size>32768){await reader.cancel();return reply(413,{message:'등록 내용이 너무 깁니다.'});}chunks.push(value);}
      let input;try{input=JSON.parse(Buffer.concat(chunks).toString('utf8'));}catch{return reply(400,{message:'입력 형식을 확인해 주세요.'});}
      if(!input||typeof input.summary!=='string'||!input.summary.trim()||input.summary.length>2000||typeof input.details!=='string'||!input.details.trim()||input.details.length>8000||input.review_with_eternian!==true)return reply(400,{message:'제목·내용과 에테르니언 공동 검토 확인이 필요합니다.'});
      const now=Date.now();const item={id:randomUUID(),summary:input.summary.trim(),details:input.details.trim(),status:'PENDING_REVIEW',created_at:new Date(now).toISOString(),review_with_eternian:true,source:'operator',execution_authorized:false};
      const key=`reports/${String(9999999999999-now).padStart(13,'0')}-${item.id}`;
      const saved=await store.setJSON(key,item,{onlyIfNew:true});
      if(saved?.modified===false)return reply(409,{message:'등록이 충돌했습니다. 다시 시도해 주세요.'});
      return reply(201,{item,message:'검토 제안을 저장했습니다. 수정·배포는 실행되지 않았습니다.'});
    }catch{return reply(503,{message:'저장소에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요. 저장·조회 성공으로 처리하지 않았습니다.'});}
  };
}
