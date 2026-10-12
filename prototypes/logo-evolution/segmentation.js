/**
 * ARKAON segmentation v0: deterministic connected-component segmentation.
 * Transparent PNG works best. Opaque photos require a supplied background color.
 * This is NOT semantic text/character understanding; confidence is heuristic.
 */
export function segmentLogo(imageData,{alphaThreshold=24,minPixels=12,maxRegions=64,background=null,colorTolerance=32}={}){
 const {width:w,height:h,data}=imageData;
 if(!Number.isInteger(w)||!Number.isInteger(h)||w<1||h<1||w*h>16_000_000||data.length!==w*h*4)throw Error("Invalid image dimensions");
 const fg=new Uint8Array(w*h);
 for(let i=0;i<w*h;i++){
  const p=i*4,a=data[p+3];
  if(a<alphaThreshold)continue;
  if(background){
   const d=Math.hypot(data[p]-background[0],data[p+1]-background[1],data[p+2]-background[2]);
   if(d<colorTolerance)continue;
  }
  fg[i]=1;
 }
 const visited=new Uint8Array(w*h),queue=new Int32Array(w*h),regions=[];
 const directions=[-1,1,-w,w];
 for(let seed=0;seed<fg.length;seed++){
  if(!fg[seed]||visited[seed])continue;
  let head=0,tail=1;queue[0]=seed;visited[seed]=1;
  let x0=w,y0=h,x1=0,y1=0,count=0;
  while(head<tail){
   const id=queue[head++],x=id%w,y=(id/w)|0;count++;
   x0=Math.min(x0,x);y0=Math.min(y0,y);x1=Math.max(x1,x);y1=Math.max(y1,y);
   for(const step of directions){
    if(step===-1&&x===0||step===1&&x===w-1||step===-w&&y===0||step===w&&y===h-1)continue;
    const n=id+step;if(!fg[n]||visited[n])continue;
    visited[n]=1;queue[tail++]=n;
   }
  }
  if(count>=minPixels)regions.push({id:regions.length+1,x:x0,y:y0,width:x1-x0+1,height:y1-y0+1,pixels:count,coverage:Number((count/(w*h)).toFixed(4))});
 }
 regions.sort((a,b)=>b.pixels-a.pixels);
 const truncated=regions.length>maxRegions;
 const selected=regions.slice(0,maxRegions);
 const foregroundPixels=fg.reduce((a,b)=>a+b,0);
 return {width:w,height:h,regions:selected,foregroundPixels,truncated,confidence:background?"low":"medium",method:"4-connected-alpha-mask",warnings:[...(!background?[]:["Background color threshold may merge or remove logo details."]),...(truncated?["Region cap reached; some components omitted."]:[]),...(selected.length<=1?["Only one connected region: manual splitting may be required."]:[])]};
}
export function drawRegionOutlines(ctx,regions,{scaleX=1,scaleY=1,offsetX=0,offsetY=0}={}){
 ctx.save();ctx.strokeStyle="#36d8ff";ctx.lineWidth=2;ctx.setLineDash([5,4]);
 for(const r of regions)ctx.strokeRect(offsetX+r.x*scaleX,offsetY+r.y*scaleY,r.width*scaleX,r.height*scaleY);
 ctx.restore();
}
