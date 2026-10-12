import {generateEditableLogo} from "./editable-logo-generator.js";
import {recordEditorCanvas,supportedVideoFormats} from "./video-export.js";
import {effectAt} from "./brush-timeline.js";
const $=id=>document.getElementById(id),stage=$("stage"),ctx=stage.getContext("2d");
let result=null,im=null,objectUrl=null,videoUrl=null,recording=false,recordTime=null,started=performance.now();
let effects={symbol01:{effect:"glow",start:0,duration:2,loop:true}};
function save(blob,name){const u=URL.createObjectURL(blob),a=document.createElement("a");a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),1500);}
async function generate(){
 $("generate").disabled=true;
 try{
  const next=await generateEditableLogo({brand:$("brand").value,accent:$("accent").value,assetId:"logoDemo01"});
  const u=URL.createObjectURL(next.sourceBlob),image=new Image();
  await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=()=>reject(Error("SVG preview failed"));image.src=u;});
  if(objectUrl)URL.revokeObjectURL(objectUrl);objectUrl=u;im=image;result=next;
  effects={symbol01:{effect:"glow",start:0,duration:2,loop:true}};
  $("layer").replaceChildren(...next.manifest.layers.map(l=>{const o=document.createElement("option");o.value=l.id;o.textContent=l.label+(l.stability==="CORE"?" [CORE]":"");return o;}));
  $("layer").value="symbol01";sync();
  $("export").disabled=!supportedVideoFormats().length;$("svg").disabled=false;$("manifest").disabled=false;
  $("summary").textContent=JSON.stringify({assetId:next.manifest.assetId,sourceHash:next.sourceHash,reviewState:next.manifest.reviewState,registration:next.registration,layers:next.manifest.layers.map(l=>({id:l.id,kind:l.kind,stability:l.stability}))},null,2);
  $("status").textContent="생성 완료: SVG + Visual_DNA 로컬 초안. 실제 생성 서비스 저장 및 승인 전 단계입니다.";
 }catch(e){$("status").textContent="생성 실패: "+e.message;}
 finally{$("generate").disabled=false;}
}
function sync(){
 const id=$("layer").value,locked=result?.manifest.layers.find(l=>l.id===id)?.stability==="CORE";
 for(const k of ["effect","start","duration","loop"])$(k).disabled=locked;
 const e=effects[id]||{effect:"none",start:0,duration:2,loop:false};
 $("effect").value=e.effect;$("start").value=e.start;$("duration").value=e.duration;$("loop").checked=e.loop;
 if(locked)$("status").textContent="CORE 구성요소: Intent_DNA 승인 없이는 수정할 수 없습니다.";
}
$("generate").onclick=generate;$("layer").onchange=sync;
for(const k of ["effect","start","duration","loop"])$(k).addEventListener("input",()=>{
 const id=$("layer").value;if(!result||result.manifest.layers.find(l=>l.id===id)?.stability==="CORE")return;
 effects[id]={effect:$("effect").value,start:Math.max(0,Math.min(5,Number($("start").value)||0)),duration:Math.max(.1,Math.min(5,Number($("duration").value)||2)),loop:$("loop").checked};
});
$("level").oninput=()=>$("levelValue").textContent=$("level").value;
function render(now){
 ctx.fillStyle="#14243c";ctx.fillRect(0,0,960,600);
 if(im&&result){
  const t=recordTime===null?(now-started)/1000:recordTime,s=.5,ox=224,oy=44;
  ctx.drawImage(im,ox,oy,512,512);
  const e=effects.symbol01,phase=effectAt(t,e),level=Number($("level").value);
  if(e&&phase.active&&level>=2&&e.effect!=="none"){
   // Clip native SVG symbol by using the SVG node's exact shape as a mask.
   const mask=document.createElement("canvas");mask.width=512;mask.height=512;
   const mc=mask.getContext("2d");
   mc.strokeStyle=result.accent;mc.lineWidth=13;mc.beginPath();mc.arc(256,177.5,69,0,Math.PI*2);mc.stroke();
   mc.fillStyle=result.accent;mc.beginPath();mc.moveTo(217.5,177.5);mc.lineTo(256,137.5);mc.lineTo(294.5,177.5);mc.lineTo(256,217.5);mc.closePath();mc.fill();
   ctx.save();
   if(e.effect==="glow"){ctx.shadowColor=result.accent;ctx.shadowBlur=25*(.5+.5*Math.sin(Math.PI*phase.progress));ctx.drawImage(mask,ox,oy);}
   if(e.effect==="pop"&&level>=4){const z=1+.1*Math.sin(Math.PI*phase.progress);ctx.translate(ox+256,oy+177.5);ctx.scale(z,z);ctx.drawImage(mask,-256,-177.5);}
   if(e.effect==="sweep"&&level>=3){
    mc.globalCompositeOperation="source-atop";const x=(phase.progress*1.5-.25)*512,g=mc.createLinearGradient(x-35,0,x+35,0);g.addColorStop(0,"#ffffff00");g.addColorStop(.5,"#ffffffbb");g.addColorStop(1,"#ffffff00");mc.fillStyle=g;mc.fillRect(0,0,512,512);ctx.drawImage(mask,ox,oy);
   }
   ctx.restore();
  }
 }
 requestAnimationFrame(render);
}
requestAnimationFrame(render);
$("export").onclick=async()=>{
 if(!result||recording)return;
 recording=true;$("export").disabled=true;recordTime=0;
 try{
  const out=await recordEditorCanvas(stage,{durationSeconds:5,fps:30,onTick:t=>{recordTime=t;}});
  if(videoUrl)URL.revokeObjectURL(videoUrl);videoUrl=URL.createObjectURL(out.blob);
  const a=$("video");a.href=videoUrl;a.download="arkaon-visual-dna."+out.extension;a.textContent=out.extension.toUpperCase()+" 다운로드";a.hidden=false;
  $("status").textContent="영상 생성 완료: "+out.mimeType;
 }catch(e){$("status").textContent="영상 생성 실패: "+e.message;}
 finally{recordTime=null;recording=false;$("export").disabled=false;}
};
$("svg").onclick=()=>result&&save(result.sourceBlob,"arkaon-editable-logo.svg");
$("manifest").onclick=()=>result&&save(new Blob([JSON.stringify({...result.manifest,previewEffects:effects},null,2)],{type:"application/json"}),"arkaon-visual-dna.json");
window.addEventListener("pagehide",()=>{if(objectUrl)URL.revokeObjectURL(objectUrl);if(videoUrl)URL.revokeObjectURL(videoUrl);});
