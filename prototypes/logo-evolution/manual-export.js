import {createComponentMasks,extractMaskedRegion} from "./precision-mask.js";
const $=id=>document.getElementById(id),stage=$("stage"),ctx=stage.getContext("2d"),src=document.createElement("canvas"),sc=src.getContext("2d",{willReadFrequently:true});
let regions=[],sprites=[],selected=-1,url=null,selection=null,drag=null,history=[],recording=false;
const levelMin={none:1,glow:2,sweep:3,pop:4};
function buildSprite(r,pixels){const c=document.createElement("canvas");c.width=r.width;c.height=r.height;c.getContext("2d").putImageData(extractMaskedRegion(pixels,r),0,0);return c;}
let sourcePixels=null;
function refresh(){sprites=regions.map(r=>buildSprite(r,sourcePixels));const list=$("list");list.replaceChildren(...regions.map((r,i)=>{const b=document.createElement("button");b.className="entry"+(selected===i?" active":"");b.textContent=`${i+1}. ${r.name||"영역"} (${r.pixels}px)`;b.onclick=()=>select(i);return b;}));$("record").disabled=!regions.length;$("undo").disabled=!history.length;}
function select(i){selected=i;const r=regions[i];$("effect").value=r?.effect||"none";$("name").value=r?.name||"";refresh();}
$("file").addEventListener("change",()=>{
 const f=$("file").files?.[0];if(!f)return;
 if(!["image/png","image/jpeg","image/webp"].includes(f.type)||f.size>8_000_000){$("status").textContent="PNG/JPEG/WebP, 8MB 이하만 허용";return;}
 const next=URL.createObjectURL(f),im=new Image();
 im.onload=()=>{
  if(im.width*im.height>16_000_000){$("status").textContent="이미지 픽셀 수 제한 초과";URL.revokeObjectURL(next);return;}
  if(url)URL.revokeObjectURL(url);url=next;
  const s=Math.min(1,1200/im.width,1200/im.height,Math.sqrt(4_000_000/(im.width*im.height)));
  src.width=Math.max(1,Math.round(im.width*s));src.height=Math.max(1,Math.round(im.height*s));sc.clearRect(0,0,src.width,src.height);sc.drawImage(im,0,0,src.width,src.height);
  sourcePixels=sc.getImageData(0,0,src.width,src.height);
  const result=createComponentMasks(sourcePixels,{minPixels:Math.max(12,Math.round(src.width*src.height*.00004))});
  regions=result.regions.map((r,i)=>({...r,name:`영역 ${i+1}`,effect:"glow"}));history=[];selection=null;select(regions.length?0:-1);
  $("status").textContent=`${regions.length}개 영역. 영역을 선택하고 사각형을 드래그해 분리할 수 있습니다.`;
 };
 im.onerror=()=>{URL.revokeObjectURL(next);$("status").textContent="이미지 로드 실패";};im.src=next;
});
function transform(){const s=Math.min(960/src.width,600/src.height);return {s,x:(960-src.width*s)/2,y:(600-src.height*s)/2};}
function pos(e){const b=stage.getBoundingClientRect();return {x:(e.clientX-b.left)*960/b.width,y:(e.clientY-b.top)*600/b.height};}
stage.addEventListener("pointerdown",e=>{if(!sourcePixels||recording)return;stage.setPointerCapture(e.pointerId);drag=pos(e);selection=null;});
stage.addEventListener("pointermove",e=>{if(!drag)return;const p=pos(e);selection={x:Math.min(drag.x,p.x),y:Math.min(drag.y,p.y),w:Math.abs(drag.x-p.x),h:Math.abs(drag.y-p.y)};});
stage.addEventListener("pointerup",e=>{if(!drag)return;const p=pos(e);selection={x:Math.min(drag.x,p.x),y:Math.min(drag.y,p.y),w:Math.abs(drag.x-p.x),h:Math.abs(drag.y-p.y)};drag=null;$("split").disabled=!(selection.w>4&&selection.h>4&&selected>=0);});
function splitRegion(region,box){
 const {s,x,y}=transform(),x0=Math.max(0,Math.floor((box.x-x)/s)),y0=Math.max(0,Math.floor((box.y-y)/s)),x1=Math.min(src.width,Math.ceil((box.x+box.w-x)/s)),y1=Math.min(src.height,Math.ceil((box.y+box.h-y)/s));
 const keep=new Uint8ClampedArray(region.alpha),cut=new Uint8ClampedArray(region.alpha);
 let nCut=0,nKeep=0;
 for(let j=0;j<region.height;j++)for(let i=0;i<region.width;i++){
  const k=j*region.width+i,inside=region.x+i>=x0&&region.x+i<x1&&region.y+j>=y0&&region.y+j<y1;
  if(inside){keep[k]=0;if(cut[k]>=24)nCut++;}else{cut[k]=0;if(keep[k]>=24)nKeep++;}
 }
 if(!nCut||!nKeep)return null;
 return [{...region,alpha:keep,pixels:nKeep},{...region,alpha:cut,pixels:nCut,name:region.name+" (분리)",effect:region.effect}];
}
$("split").onclick=()=>{if(selected<0||!selection)return;const result=splitRegion(regions[selected],selection);if(!result){$("status").textContent="분리하려면 선택 영역 안팎에 픽셀이 모두 있어야 합니다.";return;}history.push(regions.map(r=>({...r,alpha:new Uint8ClampedArray(r.alpha)})));regions.splice(selected,1,...result);selection=null;$("split").disabled=true;select(selected);$("status").textContent="선택한 픽셀 영역을 분리했습니다.";};
$("undo").onclick=()=>{if(!history.length)return;regions=history.pop();select(Math.min(selected,regions.length-1));};
$("effect").onchange=()=>{if(selected>=0)regions[selected].effect=$("effect").value;};
$("name").oninput=()=>{if(selected>=0){regions[selected].name=$("name").value;refresh();}};
$("level").oninput=()=>$("levelValue").textContent=$("level").value;
function frame(now){
 ctx.clearRect(0,0,960,600);ctx.fillStyle="#142139";ctx.fillRect(0,0,960,600);
 if(sourcePixels){
  const {s,x,y}=transform(),t=now/1000,level=Number($("level").value);ctx.drawImage(src,x,y,src.width*s,src.height*s);
  regions.forEach((r,i)=>{
   if(level<levelMin[r.effect]||r.effect==="none")return;
   const sp=sprites[i],px=x+r.x*s,py=y+r.y*s,w=r.width*s,h=r.height*s;
   ctx.save();
   if(r.effect==="glow"){ctx.shadowColor="#39d5ff";ctx.shadowBlur=14*(.7+.3*Math.sin(t*2));ctx.drawImage(sp,px,py,w,h);}
   if(r.effect==="pop"){const z=1+.10*Math.max(0,Math.sin(t*2));ctx.translate(px+w/2,py+h/2);ctx.scale(z,z);ctx.drawImage(sp,-w/2,-h/2,w,h);}
   if(r.effect==="sweep"){const scratch=document.createElement("canvas");scratch.width=r.width;scratch.height=r.height;const c=scratch.getContext("2d");c.drawImage(sp,0,0);c.globalCompositeOperation="source-atop";const q=((t*.3)%1.5)*(r.width+100)-50,g=c.createLinearGradient(q-30,0,q+30,0);g.addColorStop(0,"#ffffff00");g.addColorStop(.5,"#ffffff99");g.addColorStop(1,"#ffffff00");c.fillStyle=g;c.fillRect(0,0,r.width,r.height);ctx.drawImage(scratch,px,py,w,h);}
   ctx.restore();
  });
  if(!recording){regions.forEach((r,i)=>{ctx.strokeStyle=i===selected?"#ffd477":"#55bdf0";ctx.lineWidth=i===selected?2:1;ctx.strokeRect(x+r.x*s,y+r.y*s,r.width*s,r.height*s);});if(selection){ctx.strokeStyle="#ffe28a";ctx.lineWidth=2;ctx.strokeRect(selection.x,selection.y,selection.w,selection.h);}}
 }
 requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
$("record").onclick=async()=>{
 if(recording||!sourcePixels)return;
 if(!stage.captureStream||!window.MediaRecorder){$("status").textContent="이 브라우저는 WebM 녹화를 지원하지 않습니다.";return;}
 const preferred=["video/webm;codecs=vp9","video/webm;codecs=vp8","video/webm"].find(m=>MediaRecorder.isTypeSupported(m));
 if(!preferred){$("status").textContent="지원되는 WebM 코덱이 없습니다.";return;}
 recording=true;$("record").disabled=true;$("status").textContent="5초 녹화 중…";
 const stream=stage.captureStream(30),chunks=[],rec=new MediaRecorder(stream,{mimeType:preferred});
 rec.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};
 rec.onstop=()=>{stream.getTracks().forEach(t=>t.stop());recording=false;$("record").disabled=false;const blob=new Blob(chunks,{type:preferred}),link=$("download"),u=URL.createObjectURL(blob);if(link.dataset.url)URL.revokeObjectURL(link.dataset.url);link.dataset.url=u;link.href=u;link.download="arkaon-logo-evolution-preview.webm";link.hidden=false;link.textContent="WebM 다운로드";$("status").textContent="WebM 녹화 완료 (브라우저 미리보기 품질).";};
 rec.onerror=()=>{$("status").textContent="녹화 오류";};
 rec.start();setTimeout(()=>{if(rec.state!=="inactive")rec.stop();},5000);
};
window.addEventListener("pagehide",()=>{if(url)URL.revokeObjectURL(url);if($("download").dataset.url)URL.revokeObjectURL($("download").dataset.url);});
