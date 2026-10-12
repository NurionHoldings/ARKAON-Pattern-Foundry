import {segmentLogo,drawRegionOutlines} from "./segmentation.js";
const file=document.querySelector("#file"),canvas=document.querySelector("#canvas"),ctx=canvas.getContext("2d",{willReadFrequently:true}),status=document.querySelector("#status"),out=document.querySelector("#regions");
let img=null,url=null;
file.addEventListener("change",async()=>{
 const f=file.files?.[0];if(!f)return;
 if(!["image/png","image/jpeg","image/webp"].includes(f.type)||f.size>8_000_000){status.textContent="PNG/JPEG/WebP, 8MB 이하만 허용합니다.";return;}
 const next=URL.createObjectURL(f),i=new Image();
 i.onload=()=>{if(i.naturalWidth*i.naturalHeight>16_000_000){status.textContent="이미지 크기 제한 초과";URL.revokeObjectURL(next);return;}if(url)URL.revokeObjectURL(url);url=next;img=i;ctx.clearRect(0,0,900,500);const s=Math.min(900/i.width,500/i.height);ctx.drawImage(i,(900-i.width*s)/2,(500-i.height*s)/2,i.width*s,i.height*s);status.textContent="이미지를 불러왔습니다.";};
 i.onerror=()=>{status.textContent="파일 해석 실패";URL.revokeObjectURL(next);};i.src=next;
});
document.querySelector("#analyze").addEventListener("click",()=>{
 if(!img){status.textContent="이미지를 먼저 선택하세요.";return;}
 // Bound memory to canvas dimensions; alpha preserved in offscreen canvas.
 const s=Math.min(1,1200/img.width,1200/img.height);
 const w=Math.max(1,Math.round(img.width*s)),h=Math.max(1,Math.round(img.height*s));
 const off=document.createElement("canvas");off.width=w;off.height=h;
 const octx=off.getContext("2d",{willReadFrequently:true});octx.drawImage(img,0,0,w,h);
 const result=segmentLogo(octx.getImageData(0,0,w,h),{minPixels:Math.max(8,Math.round(w*h*.00004))});
 const displayScale=Math.min(900/w,500/h),dx=(900-w*displayScale)/2,dy=(500-h*displayScale)/2;
 ctx.clearRect(0,0,900,500);ctx.drawImage(off,dx,dy,w*displayScale,h*displayScale);
 drawRegionOutlines(ctx,result.regions,{scaleX:displayScale,scaleY:displayScale,offsetX:dx,offsetY:dy});
 status.textContent=`${result.regions.length}개 영역 검출. 신뢰도: ${result.confidence}. ${result.warnings.join(" ")}`;
 out.replaceChildren(...result.regions.map((r,i)=>{const p=document.createElement("p");p.textContent=`영역 ${i+1}: x=${r.x}, y=${r.y}, ${r.width}×${r.height}, 픽셀 ${r.pixels}`;return p;}));
});
window.addEventListener("pagehide",()=>{if(url)URL.revokeObjectURL(url);});
