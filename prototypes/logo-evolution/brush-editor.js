import {createComponentMasks,extractMaskedRegion} from "./precision-mask.js";
import {paintMask,effectAt} from "./brush-timeline.js";
const $=id=>document.getElementById(id),stage=$("stage"),ctx=stage.getContext("2d"),src=document.createElement("canvas"),sc=src.getContext("2d",{willReadFrequently:true});
let pixels=null,regions=[],selected=-1,url=null,playing=false,prev=0,brushDown=false,history=[],time=0;
const minLevel={none:1,glow:2,sweep:3,pop:4};
function bounds(){const s=Math.min(960/src.width,600/src.height);return {s,x:(960-src.width*s)/2,y:(600-src.height*s)/2};}
function position(e){const rect=stage.getBoundingClientRect(),p={x:(e.clientX-rect.left)*960/rect.width,y:(e.clientY-rect.top)*600/rect.height},{x,y,s}=bounds();return {x:Math.floor((p.x-x)/s),y:Math.floor((p.y-y)/s)};}
function sprite(r){const c=document.createElement("canvas");c.width=r.width;c.height=r.height;c.getContext("2d").putImageData(extractMaskedRegion(pixels,r),0,0);return c;}
function list(){const box=$("regions");box.replaceChildren(...regions.map((r,i)=>{const b=document.createElement("button");b.textContent=`${i+1}. ${r.name}`;b.className=i===selected?"active":"";b.onclick=()=>choose(i);return b;}));}
function choose(i){selected=i;const r=regions[i];for(const id of ["name","effect","start","duration","loop"])$(id).disabled=!r;if(r){$("name").value=r.name;$("effect").value=r.effect;$("start").value=r.start;$("duration").value=r.duration;$("loop").checked=r.loop;}list();}
$("file").onchange=()=>{
 const f=$("file").files?.[0];if(!f)return;
 if(!["image/png","image/jpeg","image/webp"].includes(f.type)||f.size>8_000_000){$("status").textContent="8MB 이하 PNG/JPEG/WebP만 지원합니다.";return;}
 const next=URL.createObjectURL(f),im=new Image();
 im.onload=()=>{
  if(im.width*im.height>16_000_000){URL.revokeObjectURL(next);$("status").textContent="픽셀 수 제한 초과";return;}
  if(url)URL.revokeObjectURL(url);url=next;
  const s=Math.min(1,1200/im.width,1200/im.height,Math.sqrt(4_000_000/(im.width*im.height)));
  src.width=Math.max(1,Math.round(im.width*s));src.height=Math.max(1,Math.round(im.height*s));sc.drawImage(im,0,0,src.width,src.height);
  pixels=sc.getImageData(0,0,src.width,src.height);
  const result=createComponentMasks(pixels,{minPixels:Math.max(12,Math.round(src.width*src.height*.00004))});
  regions=result.regions.map((r,i)=>({...r,name:`영역 ${i+1}`,effect:"glow",start:0,duration:2,loop:true}));
  history=[];time=0;$("time").value="0";choose(regions.length?0:-1);
  $("status").textContent=`${regions.length}개 영역. 브러시를 사용해 영역 마스크를 수정할 수 있습니다.`;
 };
 im.onerror=()=>{URL.revokeObjectURL(next);$("status").textContent="이미지를 읽지 못했습니다.";};im.src=next;
};
for(const id of ["name","effect","start","duration","loop"])$(id).addEventListener("input",()=>{
 if(selected<0)return;const r=regions[selected];
 if(id==="name")r.name=$("name").value.slice(0,80);
 if(id==="effect")r.effect=$("effect").value;
 if(id==="start")r.start=Math.max(0,Math.min(10,Number($("start").value)||0));
 if(id==="duration")r.duration=Math.max(.1,Math.min(10,Number($("duration").value)||2));
 if(id==="loop")r.loop=$("loop").checked;
 if(id==="name")list();
});
$("radius").oninput=()=>$("radiusLabel").textContent=$("radius").value;
$("level").oninput=()=>$("levelLabel").textContent=$("level").value;
function paint(e){
 if(!pixels||selected<0)return;
 const r=regions[selected],p=position(e),lx=p.x-r.x,ly=p.y-r.y;
 paintMask(r.alpha,r.width,r.height,{x:lx,y:ly,radius:Number($("radius").value),mode:$("mode").value});
 // Added pixels use original source alpha, preserving transparency and source colors.
 for(let y=0;y<r.height;y++)for(let x=0;x<r.width;x++){const k=y*r.width+x;if(r.alpha[k])r.alpha[k]=Math.min(r.alpha[k],pixels.data[((r.y+y)*src.width+r.x+x)*4+3]);}
 r.pixels=r.alpha.reduce((n,a)=>n+(a>=24?1:0),0);
}
stage.addEventListener("pointerdown",e=>{
 if(!pixels)return;
 if($("mode").value==="inspect"){
  const p=position(e);const hit=regions.findIndex(r=>p.x>=r.x&&p.y>=r.y&&p.x<r.x+r.width&&p.y<r.y+r.height);if(hit>=0)choose(hit);return;
 }
 if(selected<0)return;
 history.push({index:selected,alpha:new Uint8ClampedArray(regions[selected].alpha)});if(history.length>30)history.shift();
 brushDown=true;stage.setPointerCapture(e.pointerId);paint(e);
});
stage.addEventListener("pointermove",e=>{if(brushDown)paint(e);});
stage.addEventListener("pointerup",()=>brushDown=false);stage.addEventListener("pointercancel",()=>brushDown=false);
$("undo").onclick=()=>{const h=history.pop();if(!h)return;regions[h.index].alpha=h.alpha;choose(h.index);};
$("time").oninput=()=>{playing=false;$("play").textContent="재생";time=Number($("time").value);};
$("play").onclick=()=>{playing=!playing;$("play").textContent=playing?"일시정지":"재생";};
$("reset").onclick=()=>{playing=false;time=0;$("time").value="0";$("play").textContent="재생";};
function render(now){
 if(!prev)prev=now;if(playing)time=Math.min(10,time+Math.min(100,now-prev)/1000);prev=now;
 if(time>=10){playing=false;$("play").textContent="재생";}if(playing)$("time").value=time;
 $("timeLabel").textContent=time.toFixed(1)+"초";
 ctx.fillStyle="#17263b";ctx.fillRect(0,0,960,600);
 if(pixels){
  const {s,x,y}=bounds();ctx.drawImage(src,x,y,src.width*s,src.height*s);
  for(let i=0;i<regions.length;i++){
   const r=regions[i];if(+$("level").value<minLevel[r.effect]||r.effect==="none")continue;
   const phase=effectAt(time,r);if(!phase.active)continue;
   const c=sprite(r),px=x+r.x*s,py=y+r.y*s,w=r.width*s,h=r.height*s;
   ctx.save();
   if(r.effect==="glow"){ctx.shadowColor="#40cfff";ctx.shadowBlur=18*(.5+.5*Math.sin(phase.progress*Math.PI));ctx.drawImage(c,px,py,w,h);}
   if(r.effect==="pop"){const z=1+.1*Math.sin(phase.progress*Math.PI);ctx.translate(px+w/2,py+h/2);ctx.scale(z,z);ctx.drawImage(c,-w/2,-h/2,w,h);}
   if(r.effect==="sweep"){
    const temp=document.createElement("canvas");temp.width=r.width;temp.height=r.height;const tc=temp.getContext("2d");tc.drawImage(c,0,0);tc.globalCompositeOperation="source-atop";
    const center=(phase.progress*1.5-.25)*r.width,g=tc.createLinearGradient(center-25,0,center+25,0);g.addColorStop(0,"#ffffff00");g.addColorStop(.5,"#ffffff99");g.addColorStop(1,"#ffffff00");tc.fillStyle=g;tc.fillRect(0,0,r.width,r.height);ctx.drawImage(temp,px,py,w,h);
   }
   ctx.restore();
  }
  if(selected>=0){const r=regions[selected];ctx.strokeStyle="#ffd67b";ctx.lineWidth=2;ctx.strokeRect(x+r.x*s,y+r.y*s,r.width*s,r.height*s);}
 }
 requestAnimationFrame(render);
}
requestAnimationFrame(render);
$("save").onclick=()=>{
 if(!pixels)return;
 const config={schemaVersion:2,source:{width:src.width,height:src.height},level:+$("level").value,regions:regions.map(r=>({name:r.name,effect:r.effect,start:r.start,duration:r.duration,loop:r.loop,x:r.x,y:r.y,width:r.width,height:r.height,alpha:Array.from(r.alpha)}))};
 const blob=new Blob([JSON.stringify(config)],{type:"application/json"}),u=URL.createObjectURL(blob),a=document.createElement("a");a.href=u;a.download="arkaon-region-timeline.json";a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);
};
window.addEventListener("pagehide",()=>{if(url)URL.revokeObjectURL(url);});
choose(-1);
