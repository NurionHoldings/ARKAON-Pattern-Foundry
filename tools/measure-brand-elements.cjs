/* Reproducible render-only measurement; does not claim browser usability. */
const fs=require('node:fs'),path=require('node:path'),{performance}=require('node:perf_hooks'),{createHash}=require('node:crypto');
const {guardMeasureHarness}=require('./brand-browser-harness-guard.cjs');
const args=Object.fromEntries(process.argv.slice(2).reduce((a,v,i,s)=>i%2?a:[...a,[v.replace(/^--/,''),s[i+1]]],[]));
for(const key of ['baseline-dir','candidate-dir','baseline-sha','candidate-sha','out'])if(!args[key])throw Error(`Missing --${key}`);
for(const key of ['baseline-sha','candidate-sha'])if(!/^[0-9a-f]{40}$/.test(args[key]))throw Error('Full SHA required');
guardMeasureHarness(args,process.argv[1]);
const baseline=require(path.resolve(args['baseline-dir'],'services/brand-studio.js'));
const candidate=require(path.resolve(args['candidate-dir'],'services/brand-studio.js'));
const out=path.resolve(args.out);fs.mkdirSync(out,{recursive:true});
const sha=value=>createHash('sha256').update(value).digest('hex');
const briefs=[
 {businessName:'햇살 에너지',industry:'태양광 시공',audience:'건물주',services:'설치 조건 상담\n시공 범위 안내',strengths:'조건을 쉽게 설명',person:'가상 담당',email:'solar@example.com'},
 {businessName:'동네 작은 카페',industry:'카페',audience:'동네 주민',services:'커피\n브런치',strengths:'편안한 공간',person:'가상 담당',email:'cafe@example.com'},
 {businessName:'가나다라마바사아자차카타파하'.repeat(5).slice(0,60),industry:'개인 디자이너',audience:'소상공인',services:'브랜드 기획\n시각 디자인',strengths:'이해하기 쉬운 설명',person:'가상 담당',email:'design@example.com'},
].map(b=>({...b,conceptId:'horizon',symbolSize:100,logoGap:64,letterSpacing:4,logoAlign:'right',sample:true}));
const results=briefs.map((brief,i)=>{
 const row={brief_digest:sha(JSON.stringify(brief)),artifacts:{}};
 for(const [name,engine] of [['baseline',baseline],['candidate',candidate]]){
  for(let j=0;j<20;j++)engine.render(brief);
  const times=[];for(let j=0;j<100;j++){const start=performance.now();engine.render(brief);times.push(performance.now()-start);}times.sort((a,b)=>a-b);
  const html=engine.render(brief),filename=`brief-${i+1}-${name}.html`;fs.writeFileSync(path.join(out,filename),html);
  row.artifacts[name]={path:filename,sha256:sha(html),render_ms_median:times[50],render_ms_p95:times[95],iterations:100};
 }
 return row;
});
const manifest={schema_version:'apf.brand-element-sandbox-evidence/v1',created_at:new Date().toISOString(),baseline_commit:args['baseline-sha'],candidate_code_commit:args['candidate-sha'],contributor:'ETERNIAN_IMPLEMENTATION',independent_audit_status:'NOT_RUN',arkaon_first_verification:'NOT_RUN',improvement_accepted:false,environment:{node:process.version,platform:process.platform},measurement_scope:'NODE_RENDER_ONLY',results,planned_browser_widths:[360,390,768,1440],browser_12_condition_comparison:'NOT_RUN',browser_undo_redo:'NOT_RUN',browser_save_reopen:'NOT_RUN',ci_run_id:null,rollback:'Revert sandbox PR; preserve existing project data'};
fs.writeFileSync(path.join(out,'manifest.json'),JSON.stringify(manifest,null,2)+'\n');console.log(JSON.stringify({briefs:results.length,measurement_scope:manifest.measurement_scope,out}));
