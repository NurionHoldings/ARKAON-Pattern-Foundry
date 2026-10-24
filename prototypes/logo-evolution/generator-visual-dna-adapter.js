import {createVisualDna,planVisualEdit} from "./visual-dna.js";
const sha=async bytes=>Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",bytes))).map(x=>x.toString(16).padStart(2,"0")).join("");
/**
 * Called immediately after a generator returns a structured result.
 * It MUST provide actual editable layer references, not fabricated segmentation.
 * Sidecar stays DRAFT until an authorized server review promotes it.
 */
export async function registerGeneratedLogo({assetId,revision=1,intentFingerprint,intentAxes,sourceBlob,canvas,layers}){
 if(!(sourceBlob instanceof Blob)||sourceBlob.size===0||sourceBlob.size>8_000_000)throw Error("Invalid source blob");
 if(!["image/png","image/webp","image/jpeg","image/svg+xml"].includes(sourceBlob.type))throw Error("Unsupported source type");
 const sourceHash=await sha(await sourceBlob.arrayBuffer());
 const manifest=createVisualDna({assetId,version:revision,intentFingerprint,intentAxes,canvas,layers,sourceHash});
 return {manifest,sourceBlob,sourceHash,revision,registration:"LOCAL_DRAFT",readyForProduction:false};
}
export async function registerRasterFallback({assetId,revision=1,intentFingerprint,intentAxes,sourceBlob,canvas}){
 const record=await registerGeneratedLogo({assetId,revision,intentFingerprint,intentAxes,sourceBlob,canvas,layers:[{
  id:"rasterFallback01",kind:"group",label:"전체 이미지 (의미 미검증)",stability:"EXPERIMENTAL",
  bounds:{x:0,y:0,width:canvas.width,height:canvas.height},intentLinks:["OBJECT","EVOLUTION"],
  source:{type:"raster-mask",ref:"generated/full-image-mask"}
 }]});
 record.manifest.layers[0].semanticStatus="UNVERIFIED_RASTER";
 return record;
}
export function locateEditPoint(manifest,layerId,operation){
 return planVisualEdit(manifest,{layerId,operation});
}
export function serializeRegistration(record){
 const payload={manifest:record.manifest,sourceHash:record.sourceHash,revision:record.revision,registration:record.registration};
 return JSON.stringify(payload,null,2);
}
