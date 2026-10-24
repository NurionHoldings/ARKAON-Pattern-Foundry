import {segmentLogo} from "./segmentation.js";
const $=id=>document.getElementById(id),canvas=$("canvas"),ctx=canvas.getContext("2d");
const off=document.createElement("canvas"),oc=off.getContext("2d",{willReadFrequently:true});
let image=null,url=null,regions=[],selected=-1,playing=true,raf=0,elapsed=0,last=0,origin=null;
const thresholds={none:1,glow:2,color:2,sweep:3,pop:4,pulse:5};
const cap=64;
function fit(){if(!image)return;const s=Math.min(960/image.width,600/image.height);return {x:(960-image.width*s)/2,y:(600-image.height*s)/2,s};}
function render(ts){
 if(!last)last=ts;if(playing)elapsed+=Math.min(100,ts-last)/1000;last=ts;
 ctx.clearRect(0,0,960,600);ctx.fillStyle="#142039";ctx.fillRect(0,0,960,600);
 if(image){
  const {x,y,s}=fit();ctx.drawImage(image,x,y,image.width*s,image.height*s);
  const level=+$("level").value,intensity=$("intensity").value,amp=intensity==="vivid"?1.3:intensity==="natural"?.6:1;
  for(let i=0;i<regions.length;i++){
   const r=regions[i];if(!r.enabled||level<thresholds[r.effect]||r.effect==="none")continue;
   // Cropped bounding-box preview. Connected components may contain transparent pixels
   // and overlapping boxes; final engine will require per-pixel segmentation masks.
   const sx=r.x,sy=r.y,sw=r.width,sh=r.height,dx=x+sx*s,dy=y+sy*s,dw=sw*s,dh=sh*s;
   ctx.save();
   if(r.effect==="pop"){const sc=1+.10*Math.pow(Math.max(0,Math.sin(elapsed*2.3)),2)*amp;ctx.translate(dx+dw/2,dy+dh/2);ctx.scale(sc,sc);ctx.drawImage(off,sx,sy,sw,sh,-dw/2,-dh/2,dw,dh);}
   if(r.effect==="glow"){ctx.shadowColor="#48caff";ctx.shadowBlur=20*amp;ctx.drawImage(off,sx,sy,sw,sh,dx,dy,dw,dh);}
   if(r.effect==="color"){ctx.globalAlpha=.14*amp*(.5+.5*Math.sin(elapsed*2));ctx.fillStyle="#60bfff";ctx.fillRect(dx,dy,dw,dh);}
   if(r.effect==="sweep"){ctx.beginPath();ctx.rect(dx,dy,dw,dh);ctx.clip();const pos=dx-50+((elapsed*.45)%1.5)*(dw+100);const grad=ctx.createLinearGradient(pos-40,0,pos+40,0);grad.addColorStop(0,"#ffffff00");grad.addColorStop(.5,"#ffffff70");grad.addColorStop(1,"#ffffff00");ctx.fillStyle=grad;ctx.fillRect(dx,dy,dw,dh);}
   if(r.effect==="pulse"){ctx.strokeStyle="#65d7ff";ctx.globalAlpha=.35*amp;ctx.lineWidth=2;ctx.strokeRect(dx-4-Math.sin(elapsed*2)*6,dy-4-Math.sin(elapsed*2)*6,dw+8+Math.sin(elapsed*2)*12,dh+8+Math.sin(elapsed*2)*12);}
   ctx.restore();
  }
  for(let i=0;i<regions.length;i++){const r=regions[i];ctx.strokeStyle=i===selected?"#ffcf6d":"#58c6ff";ctx.lineWidth=i===selected?3:1;ctx.strokeRect(x+r.x*s,y+r.y*s,r.width*s,r.height*s);}
 }
 raf=requestAnimationFrame(render);
}
function select(i){
 selected=i;const r=regions[i];$("name").disabled=$("effect").disabled=$("enabled").disabled=!r;
 if(r){$("name").value=r.name;$("effect").value=r.effect;$("enabled").checked=r.enabled;}
 document.querySelectorAll(".region button").forEach((b,j)=>b.classList.toggle("active",i===j));
}
function regionList(){
 const wrap=$("regions");wrap.replaceChildren();
 for(let i=0;i<regions.length;i++){
  const r=regions[i],row=document.createElement("div"),button=document.createElement("button");
  row.className="region";button.textContent=`${i+1}. ${r.name}`;button.type="button";button.addEventListener("click",()=>select(i));row.append(button);wrap.append(row);
 }
 if(!regions.length)wrap.textContent="분리 가능한 영역이 없습니다.";
 select(regions.length?0:-1);
}
$("file").addEventListener("change",()=>{
 const f=$("file").files?.[0];if(!f)return;
 if(!["image/png","image/jpeg","image/webp"].includes(f.type)||f.size>8*1024*1024){$("status").textContent="지원 파일은 PNG/JPEG/WebP, 8MB 이하입니다.";return;}
 const next=URL.createObjectURL(f),img=new Image();
 img.onload=()=>{
  if(img.width*img.height>16_000_000){$("status").textContent="이미지 픽셀 수 제한을 초과했습니다.";URL.revokeObjectURL(next);return;}
  if(url)URL.revokeObjectURL(url);url=next;image=img;
  const s=Math.min(1,1200/img.width,1200/img.height);off.width=Math.max(1,Math.round(img.width*s));off.height=Math.max(1,Math.round(img.height*s));
  oc.clearRect(0,0,off.width,off.height);oc.drawImage(img,0,0,off.width,off.height);
  const result=segmentLogo(oc.getImageData(0,0,off.width,off.height),{minPixels:Math.max(12,Math.round(off.width*off.height*.00004)),maxRegions:cap});
  // Region boxes are in offscreen coordinates, so render using the same offscreen image.
  origin=img;image=off;
  regions=result.regions.map((r,i)=>({...r,name:`영역 ${i+1}`,effect:"glow",enabled:true}));
  regionList();
  $("status").textContent=`${regions.length}개 영역 검출. ${result.warnings.join(" ")} 원본 이미지는 수정되지 않습니다.`;
 };
 img.onerror=()=>{$("status").textContent="이미지 로드에 실패했습니다.";URL.revokeObjectURL(next);};img.src=next;
});
for(const [id,key] of [["name","name"],["effect","effect"],["enabled","enabled"]])$(id).addEventListener("input",()=>{
 if(selected<0)return;regions[selected][key]=key==="enabled"?$(id).checked:$(id).value;
 if(key==="name")document.querySelectorAll(".region button")[selected].textContent=`${selected+1}. ${regions[selected].name}`;
});
$("level").addEventListener("input",()=>$("levelLabel").textContent=$("level").value);
$("play").addEventListener("click",()=>{playing=!playing;$("play").textContent=playing?"일시정지":"재생";});
$("download").addEventListener("click",()=>{
 if(!image){$("status").textContent="이미지를 먼저 불러오세요.";return;}
 const config={schemaVersion:1,level:+$("level").value,intensity:$("intensity").value,source:{width:image.width,height:image.height},regions:regions.map(({id,x,y,width,height,name,effect,enabled})=>({id,x,y,width,height,name,effect,enabled})),previewOnly:true};
 const blob=new Blob([JSON.stringify(config,null,2)],{type:"application/json"}),u=URL.createObjectURL(blob),a=document.createElement("a");a.href=u;a.download="arkaon-logo-evolution-config.json";a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);
});
canvas.addEventListener("click",e=>{
 if(!image)return;const rect=canvas.getBoundingClientRect(),px=(e.clientX-rect.left)*canvas.width/rect.width,py=(e.clientY-rect.top)*canvas.height/rect.height,{x,y,s}=fit();
 const hits=regions.map((r,i)=>({i,r})).filter(({r})=>px>=x+r.x*s&&px<=x+(r.x+r.width)*s&&py>=y+r.y*s&&py<=y+(r.y+r.height)*s);
 if(hits.length)select(hits.sort((a,b)=>a.r.width*a.r.height-b.r.width*b.r.height)[0].i);
});
$("name").disabled=$("effect").disabled=$("enabled").disabled=true;
window.addEventListener("pagehide",()=>{cancelAnimationFrame(raf);if(url)URL.revokeObjectURL(url);});
if(matchMedia("(prefers-reduced-motion: reduce)").matches)playing=false;
raf=requestAnimationFrame(render);
