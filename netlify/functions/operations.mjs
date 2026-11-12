import { getStore } from '@netlify/blobs';
import session from './operator-session.mjs';
import { createOperationsHandler } from '../lib/operations.mjs';
export default async (request,context)=>createOperationsHandler({
  authorize:input=>session(new Request(new URL('/api/operator-session',input.url),{headers:{cookie:input.headers.get('cookie')||''}})),
  openStore:()=>{
    if(!context?.deploy?.id||!context.deploy.context)throw new Error('Missing deployment context');
    const name=context.deploy.context==='production'?'arkaon-review-documents':`arkaon-review-preview-${context.deploy.id}`;
    return getStore({name,consistency:'strong'});
  },
})(request);
export const config={path:['/api/operations/health','/api/operations/mailbox'],rateLimit:{action:'rate_limit',aggregateBy:['ip','domain'],windowSize:60,windowLimit:60}};
