import {createComponentMasks,extractMaskedRegion} from "./precision-mask.js";
const $=id=>document.getElementById(id),canvas=$("canvas"),ctx=canvas.getContext("2d");
let src=null,regions=[],sprites=[],url=null,start=performance.now();
const requirements={glow:2,color:2,sweep:3,pop:4};
$("file").addEventListener("change",()=>{
 const f=$("file").files?.[0];if(!f)return;
 if(!["image/png","image/jpeg","image/webp"].includes(f.type)||f.size>8*1024*1024){$("status").textContent="8MB 이하 PNG/JPEG/WebP만 지원합니다.";return;}
 const next=URL.createObjectURL(f),image=new Image();
 image.onload=()=>{
  if(image.width*image.height>16_000_000){$("status").textContent="이미지 크기 제한 초과";URL.revokeObjectURL(next);return;}
  if(url)URL.revokeObjectURL(url);url=next;
  const s=Math.min(1,1600/image.width,1600/image.height,Math.sqrt(4_000_000/(image.width*image.height)));
  const off=document.createElement("canvas");off.width=Math.max(1,Math.round(image.width*s));off.height=Math.max(1,Math.round(image.height*s));
  const oc=off.getContext("2d",{willReadFrequently:true});oc.drawImage(image,0,0,off.width,off.height);
  const pixels=oc.getImageData(0,0,off.width,off.height);
  const result=createComponentMasks(pixels,{minPixels:Math.max(12,Math.round(off.width*off.height*.00004))});
  src=off;regions=result.regions;sprites=regions.map(r=>{
   const c=document.createElement("canvas");c.width=r.width;c.height=r.height;c.getContext("2d").putImageData(extractMaskedRegion(pixels,r),0,0);return c;
  });
  $("region").replaceChildren(...regions.map((r,i)=>{const opt=document.createElement("option");opt.value=i;opt.textContent=`영역 ${i+1} (${r.pixels}픽셀)`;return opt;}));
  $("status").textContent=`${regions.length}개 정밀 픽셀 마스크 생성. ${result.truncated?"최대 영역 수 초과.":""} 영역이 연결되어 있으면 수동 분리가 필요합니다.`;
 };
 image.onerror=()=>{$("status").textContent="이미지 로드 실패";URL.revokeObjectURL(next);};image.src=next;
});
$("level").addEventListener("input",()=>$("levelLabel").textContent=$("level").value);
function render(now){
 ctx.clearRect(0,0,960,600);ctx.fillStyle="#13243b";ctx.fillRect(0,0,960,600);
 if(src){
  const s=Math.min(960/src.width,600/src.height),ox=(960-src.width*s)/2,oy=(600-src.height*s)/2;
  ctx.drawImage(src,ox,oy,src.width*s,src.height*s);
  const idx=Number($("region").value),r=regions[idx],sprite=sprites[idx],effect=$("effect").value,level=Number($("level").value),t=(now-start)/1000;
  if(r&&sprite&&level>=requirements[effect]){
   const x=ox+r.x*s,y=oy+r.y*s,w=r.width*s,h=r.height*s;
   ctx.save();
   if(effect==="glow"){
    ctx.shadowColor="#48d3ff";ctx.shadowBlur=20*(.7+.3*Math.sin(t*2));ctx.drawImage(sprite,x,y,w,h);
   }else if(effect==="pop"){
    const z=1+.10*Math.pow(Math.max(0,Math.sin(t*2)),2);ctx.translate(x+w/2,y+h/2);ctx.scale(z,z);ctx.drawImage(sprite,-w/2,-h/2,w,h);
   }else{
    // Isolate effect to component alpha using a temporary canvas.
    const temp=document.createElement("canvas");temp.width=r.width;temp.height=r.height;
    const tc=temp.getContext("2d");tc.drawImage(sprite,0,0);
    tc.globalCompositeOperation="source-atop";
    if(effect==="color"){tc.fillStyle=`rgba(62,185,255,${.22*(.5+.5*Math.sin(t*2))})`;tc.fillRect(0,0,r.width,r.height);}
    if(effect==="sweep"){
     const px=((t*.3)%1.5)*(r.width+100)-50;
     const grad=tc.createLinearGradient(px-35,0,px+35,0);grad.addColorStop(0,"#ffffff00");grad.addColorStop(.5,"#ffffff99");grad.addColorStop(1,"#ffffff00");tc.fillStyle=grad;tc.fillRect(0,0,r.width,r.height);
    }
    ctx.drawImage(temp,x,y,w,h);
   }
   ctx.restore();
   ctx.strokeStyle="#ffd479";ctx.setLineDash([5,5]);ctx.strokeRect(x,y,w,h);ctx.setLineDash([]);
  }
 }
 requestAnimationFrame(render);
}
requestAnimationFrame(render);
window.addEventListener("pagehide",()=>{if(url)URL.revokeObjectURL(url);});
