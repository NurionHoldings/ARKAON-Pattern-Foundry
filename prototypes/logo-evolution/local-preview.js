// ARKAON Logo Evolution Engine: client-side preview only.
// No uploads, payments, persistence, or server calls. User-provided image remains local.
import {resolveLogoEvolution} from "./logo-evolution-widget.js";
const canvas=document.querySelector("#stage");
const ctx=canvas.getContext("2d");
const input=document.querySelector("#imageInput");
const level=document.querySelector("#previewLevel");
const type=document.querySelector("#previewType");
const intensity=document.querySelector("#previewIntensity");
const play=document.querySelector("#play");
const notice=document.querySelector("#previewNotice");
let img=null,sourceUrl=null,playing=true,frameId=0,started=performance.now();
const reduced=matchMedia("(prefers-reduced-motion: reduce)");
const loadImage=url=>new Promise((resolve,reject)=>{
 const image=new Image();image.onload=()=>resolve(image);image.onerror=()=>reject(new Error("이미지를 읽지 못했습니다"));image.src=url;
});
input.addEventListener("change",async()=>{
 const file=input.files?.[0];if(!file)return;
 if(!["image/png","image/jpeg","image/webp"].includes(file.type)){notice.textContent="PNG/JPEG/WebP 파일만 지원합니다.";return;}
 if(file.size>8*1024*1024){notice.textContent="파일 크기는 8MB 이하로 제한됩니다.";return;}
 const url=URL.createObjectURL(file);
 try{
  const candidate=await loadImage(url);
  if(candidate.naturalWidth*candidate.naturalHeight>16000000)throw new Error("이미지 픽셀 수 제한(1600만)을 초과했습니다.");
  if(sourceUrl)URL.revokeObjectURL(sourceUrl);
  sourceUrl=url;img=candidate;notice.textContent="로컬 이미지 로드 완료. 원본 파일은 수정되지 않습니다.";
 }catch(e){URL.revokeObjectURL(url);notice.textContent=e.message;}
});
play.addEventListener("click",()=>{playing=!playing;play.textContent=playing?"일시정지":"재생";});
function render(now){
 const w=canvas.width,h=canvas.height;
 ctx.clearRect(0,0,w,h);ctx.fillStyle="#101a2b";ctx.fillRect(0,0,w,h);
 const config=resolveLogoEvolution({level:level.value,logoType:type.value,intensity:intensity.value});
 const t=playing&&!reduced.matches?(now-started)/1000:0;
 const baseScale=Math.min((w*.76)/(img?.naturalWidth||420),(h*.70)/(img?.naturalHeight||240));
 const iw=(img?.naturalWidth||420)*baseScale,ih=(img?.naturalHeight||240)*baseScale;
 const amp=config.intensity==="vivid"?1.3:config.intensity==="natural"?.6:1;
 const has=e=>config.supportedEffects.includes(e);
 let scale=1;
 if(has("depth_pop"))scale=1+.10*Math.pow(Math.max(0,Math.sin(t*2.2)),2)*amp;
 ctx.save();ctx.translate(w/2,h/2);ctx.scale(scale,scale);
 if(config.level>=2){
  const glow=has("outline_neon")?16:7;
  ctx.shadowColor="#46c8ff";ctx.shadowBlur=glow*(.7+.3*Math.sin(t*2))*amp;
 }
 if(img){ctx.drawImage(img,-iw/2,-ih/2,iw,ih);}
 else{ctx.font="bold 60px system-ui";ctx.textAlign="center";ctx.textBaseline="middle";ctx.fillStyle="#d7ebff";ctx.fillText("MY LOGO",0,0);}
 ctx.shadowBlur=0;
 if(has("specular_sweep")||has("material_reflection")){
  // Clipped to the source's alpha; text placeholder uses a rectangular fallback.
  ctx.save();
  if(img){ctx.globalCompositeOperation="source-atop";}
  const x=-iw/2+((t*.22)%1.5)*iw*1.8;
  const gradient=ctx.createLinearGradient(x-55,0,x+55,0);
  gradient.addColorStop(0,"rgba(255,255,255,0)");gradient.addColorStop(.5,`rgba(255,255,255,${.24*amp})`);gradient.addColorStop(1,"rgba(255,255,255,0)");
  ctx.fillStyle=gradient;ctx.fillRect(-iw/2,-ih/2,iw,ih);ctx.restore();
 }
 ctx.restore();
 if(has("radial_wave")||has("trace_current")){
  ctx.strokeStyle=`rgba(86,195,255,${.25*amp})`;ctx.lineWidth=2;
  const radius=40+((t*40)%140);ctx.beginPath();ctx.ellipse(w/2,h/2,radius,radius*.6,0,0,Math.PI*2);ctx.stroke();
 }
 if(playing&&!reduced.matches)frameId=requestAnimationFrame(render);
}
function restart(){cancelAnimationFrame(frameId);render(performance.now());}
for(const el of [level,type,intensity])el.addEventListener("input",restart);
reduced.addEventListener("change",restart);
document.addEventListener("visibilitychange",()=>{if(document.hidden){cancelAnimationFrame(frameId);}else restart();});
function tick(now){render(now);if(playing&&!reduced.matches)frameId=requestAnimationFrame(tick);}
function startLoop(){cancelAnimationFrame(frameId);const step=now=>{render(now);if(playing&&!reduced.matches)frameId=requestAnimationFrame(step);};frameId=requestAnimationFrame(step);}
for(const el of [level,type,intensity])el.addEventListener("input",startLoop);
play.addEventListener("click",startLoop);
reduced.addEventListener("change",startLoop);
startLoop();
window.addEventListener("pagehide",()=>{cancelAnimationFrame(frameId);if(sourceUrl)URL.revokeObjectURL(sourceUrl);});
