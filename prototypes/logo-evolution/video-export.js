export function supportedVideoFormats(){
 if(typeof MediaRecorder==="undefined")return [];
 return ["video/mp4;codecs=avc1.42E01E","video/webm;codecs=vp9","video/webm;codecs=vp8","video/webm"].filter(t=>MediaRecorder.isTypeSupported(t));
}
export function recordEditorCanvas(canvas,{durationSeconds=5,fps=30,onTick}={}){
 if(!canvas?.captureStream||!supportedVideoFormats().length)throw Error("Unsupported video recording");
 if(durationSeconds<1||durationSeconds>10||![24,30].includes(fps))throw Error("Invalid recording settings");
 const mimeType=supportedVideoFormats()[0],stream=canvas.captureStream(fps),rec=new MediaRecorder(stream,{mimeType}),chunks=[];
 return new Promise((resolve,reject)=>{
  let finished=false;const clean=()=>stream.getTracks().forEach(t=>t.stop());
  rec.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};
  rec.onerror=()=>{if(!finished){finished=true;clean();reject(Error("Recording failed"));}};
  rec.onstop=()=>{if(finished)return;finished=true;clean();const blob=new Blob(chunks,{type:mimeType});if(!blob.size)return reject(Error("Empty recording"));resolve({blob,mimeType,extension:mimeType.startsWith("video/mp4")?"mp4":"webm",mode:"BROWSER_REALTIME"});};
  rec.start(250);const begin=performance.now();
  const tick=now=>{if(finished)return;const t=Math.min(durationSeconds,(now-begin)/1000);try{onTick?.(t);}catch(err){finished=true;rec.stop();clean();reject(err);return;}if(t>=durationSeconds)rec.stop();else requestAnimationFrame(tick);};
  requestAnimationFrame(tick);
 });
}
