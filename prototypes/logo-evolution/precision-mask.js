/**
 * Precise per-pixel connected-component masks. Deterministic alpha segmentation,
 * not semantic AI. Memory bounded by max 4 megapixels for preview processing.
 */
export function createComponentMasks(imageData,{alphaThreshold=24,minPixels=12,maxRegions=64}={}){
 const {width:w,height:h,data}=imageData;
 if(!Number.isInteger(w)||!Number.isInteger(h)||w<1||h<1||w*h>4_000_000||data.length!==w*h*4)throw Error("Image too large or invalid");
 const count=w*h,visited=new Uint8Array(count),queue=new Int32Array(count),components=[];
 for(let seed=0;seed<count;seed++){
  if(visited[seed]||data[seed*4+3]<alphaThreshold)continue;
  let head=0,tail=1;queue[0]=seed;visited[seed]=1;
  let minX=w,minY=h,maxX=0,maxY=0;
  while(head<tail){
   const p=queue[head++],x=p%w,y=(p/w)|0;
   if(x<minX)minX=x;if(y<minY)minY=y;if(x>maxX)maxX=x;if(y>maxY)maxY=y;
   for(const n of [x>0?p-1:-1,x<w-1?p+1:-1,y>0?p-w:-1,y<h-1?p+w:-1]){
    if(n<0||visited[n]||data[n*4+3]<alphaThreshold)continue;
    visited[n]=1;queue[tail++]=n;
   }
  }
  if(tail<minPixels)continue;
  const rw=maxX-minX+1,rh=maxY-minY+1,alpha=new Uint8ClampedArray(rw*rh);
  for(let k=0;k<tail;k++){
   const p=queue[k],x=p%w-minX,y=((p/w)|0)-minY;
   alpha[y*rw+x]=data[p*4+3];
  }
  components.push({x:minX,y:minY,width:rw,height:rh,pixels:tail,alpha});
 }
 components.sort((a,b)=>b.pixels-a.pixels);
 return {width:w,height:h,regions:components.slice(0,maxRegions).map((r,i)=>({...r,id:i+1})),truncated:components.length>maxRegions,method:"per-pixel-4-connected-alpha"};
}
/** Returns RGBA pixels masked to precisely the chosen component. */
export function extractMaskedRegion(imageData,region){
 const {width:w,data}=imageData,{x,y,width:rw,height:rh,alpha}=region;
 const output=new ImageData(rw,rh);
 for(let j=0;j<rh;j++)for(let i=0;i<rw;i++){
  const si=((y+j)*w+x+i)*4,di=(j*rw+i)*4,a=alpha[j*rw+i];
  output.data[di]=data[si];output.data[di+1]=data[si+1];output.data[di+2]=data[si+2];output.data[di+3]=a;
 }
 return output;
}
