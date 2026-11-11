import { createHash, createHmac, timingSafeEqual } from 'node:crypto';

const cookieName = '__Host-apf_operator';
const digest = value => createHash('sha256').update(value).digest();
const equal = (a,b) => timingSafeEqual(digest(a),digest(b));
const sign = (body,secret) => createHmac('sha256',secret).update(body).digest('hex');
const headers = {'Cache-Control':'no-store','Content-Type':'application/json; charset=utf-8','X-Content-Type-Options':'nosniff'};
const reply = (status,message,extra={}) => new Response(status===204?null:JSON.stringify({message}),{status,headers:{...headers,...extra}});

export default async function handler(request) {
  const password = Netlify.env.get('APF_ADMIN_PASSWORD');
  if (!password || password.length<16) return reply(503,'관리자 비밀번호 설정이 필요합니다.');
  const url = new URL(request.url);
  const secret = digest(password);
  if(request.method==='GET') {
    const token=(request.headers.get('cookie')||'').split(';').map(x=>x.trim()).find(x=>x.startsWith(`${cookieName}=`))?.slice(cookieName.length+1)||'';
    const [expires,mac]=token.split('.');
    const expiry=Number(expires);
    const body=`${url.host}:${expires}`;
    if(!/^\d+$/.test(expires||'') || !Number.isSafeInteger(expiry) || expiry<=Math.floor(Date.now()/1000) || expiry>Math.floor(Date.now()/1000)+3600 || !mac || !equal(mac,sign(body,secret)))return reply(401,'비밀번호를 입력해 주세요.');
    return reply(204);
  }
  if(request.headers.get('origin')!==url.origin)return reply(403,'잘못된 요청입니다.');
  if(request.method==='DELETE')return reply(204,null,{'Set-Cookie':`${cookieName}=; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=0`});
  if(request.method!=='POST')return reply(405,'허용되지 않은 요청입니다.',{Allow:'GET, POST, DELETE'});
  if(!request.headers.get('content-type')?.startsWith('application/json'))return reply(415,'JSON 요청이 필요합니다.');
  let input;
  try{const raw=await request.text();if(raw.length>2048)return reply(413,'입력이 너무 깁니다.');input=JSON.parse(raw);}catch{return reply(400,'입력을 확인해 주세요.');}
  if(!input || typeof input.password!=='string'||input.password.length>512||!equal(input.password,password))return reply(401,'비밀번호를 확인해 주세요.');
  const expires=String(Math.floor(Date.now()/1000)+3600);
  const token=`${expires}.${sign(`${url.host}:${expires}`,secret)}`;
  return reply(204,null,{'Set-Cookie':`${cookieName}=${token}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=3600`});
}

export const config={path:'/api/operator-session',rateLimit:{action:'rate_limit',aggregateBy:['ip','domain'],windowSize:60,windowLimit:15}};
