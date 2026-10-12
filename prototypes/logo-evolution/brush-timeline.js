/**
 * Manual mask brush + deterministic timeline utilities.
 * Input masks are mutable Uint8ClampedArray alpha planes (0..255).
 * No backend, auth, payment or ffmpeg integration.
 */
export function paintMask(mask,width,height,{x,y,radius=8,mode="add"}){
 if(mask.length!==width*height)throw Error("Invalid mask");
 const cx=Math.round(x),cy=Math.round(y),r=Math.max(1,Math.min(100,Math.round(radius)));
 for(let py=Math.max(0,cy-r);py<Math.min(height,cy+r+1);py++)for(let px=Math.max(0,cx-r);px<Math.min(width,cx+r+1);px++){
  if((px-cx)**2+(py-cy)**2<=r*r)mask[py*width+px]=mode==="erase"?0:255;
 }
 return mask;
}
export function effectAt(time,{start=0,duration=2,loop=false}={}){
 if(!Number.isFinite(time)||!Number.isFinite(start)||!Number.isFinite(duration)||duration<=0)throw Error("Invalid timeline");
 const elapsed=time-start;
 if(elapsed<0)return {active:false,progress:0};
 if(loop)return {active:true,progress:(elapsed%duration)/duration};
 return {active:elapsed<=duration,progress:Math.min(1,elapsed/duration)};
}
export function normalizedRegion(region){
 return {id:region.id,name:String(region.name||"영역").slice(0,80),x:region.x,y:region.y,width:region.width,height:region.height,effect:region.effect||"none",start:Number(region.start)||0,duration:Math.max(.1,Math.min(60,Number(region.duration)||2)),loop:Boolean(region.loop)};
}
