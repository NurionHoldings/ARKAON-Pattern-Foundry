/**
 * Draft asset-local Visual DNA manifest produced AT GENERATION TIME.
 * Does not mutate the platform's locked Intent_DNA contract.
 * No inferred semantic parts: generator must supply explicit editable layers.
 */
export const VISUAL_DNA_SCHEMA="arkaon.visual-dna/v1";
const AXES=["WHY","WHO","VALUE","OUTCOME","JOURNEY","OBJECT","OWNER","INVARIANT","CONSTRAINT","RISK","SIGNAL","EVOLUTION"];
const allowedKinds=new Set(["text","symbol","outline","decoration","background","light","group"]);
const allowedRoles=new Set(["CORE","CONFIGURABLE","EXPERIMENTAL"]);
const safeId=x=>typeof x==="string"&&/^[a-zA-Z][a-zA-Z0-9_-]{0,79}$/.test(x);
const unique=x=>new Set(x).size===x.length;
function assert(ok,message){if(!ok)throw new Error(message);}
export function createVisualDna({assetId,version=1,intentFingerprint,intentAxes,canvas,layers,sourceHash,createdBy="generator"}){
 assert(safeId(assetId),"Invalid assetId");
 assert(Number.isInteger(version)&&version>0,"Invalid version");
 assert(typeof intentFingerprint==="string"&&/^[a-f0-9]{64}$/i.test(intentFingerprint),"Invalid intent fingerprint");
 assert(typeof sourceHash==="string"&&/^[a-f0-9]{64}$/i.test(sourceHash),"Invalid source hash");
 assert(canvas&&Number.isInteger(canvas.width)&&Number.isInteger(canvas.height)&&canvas.width>0&&canvas.height>0&&canvas.width*canvas.height<=16_000_000,"Invalid canvas");
 assert(Array.isArray(layers)&&layers.length>0&&layers.length<=256,"Invalid layers");
 assert(intentAxes&&typeof intentAxes==="object"&&AXES.every(a=>Array.isArray(intentAxes[a])),"12 Intent_DNA axes required");
 const ids=layers.map(l=>l.id);assert(ids.every(safeId)&&unique(ids),"Layer IDs must be unique and stable");
 const validated=layers.map(l=>{
  assert(allowedKinds.has(l.kind),"Invalid layer kind");
  assert(allowedRoles.has(l.stability),"Invalid stability");
  assert(typeof l.label==="string"&&l.label.length>0&&l.label.length<=120,"Invalid layer label");
  assert(l.bounds&&["x","y","width","height"].every(k=>Number.isFinite(l.bounds[k])),"Invalid bounds");
  const {x,y,width,height}=l.bounds;
  assert(x>=0&&y>=0&&width>0&&height>0&&x+width<=canvas.width&&y+height<=canvas.height,"Layer out of bounds");
  assert(Array.isArray(l.intentLinks)&&l.intentLinks.length>0&&l.intentLinks.every(a=>AXES.includes(a)),"Intent links required");
  assert(l.source&&["svg-node","raster-mask","text-run"].includes(l.source.type),"Editable source reference required");
  assert(typeof l.source.ref==="string"&&l.source.ref.length>0&&l.source.ref.length<=256&&!l.source.ref.includes(".."),"Invalid source reference");
  return {id:l.id,kind:l.kind,label:l.label,stability:l.stability,bounds:{x,y,width,height},intentLinks:[...new Set(l.intentLinks)],source:{type:l.source.type,ref:l.source.ref},editable:l.stability!=="CORE",effectsAllowed:l.stability!=="CORE"};
 });
 return {schema:VISUAL_DNA_SCHEMA,assetId,version,createdBy,sourceHash,canvas:{width:canvas.width,height:canvas.height},intent:{fingerprint:intentFingerprint,axes:intentAxes,approved:false},layers:validated,reviewState:"DRAFT",createdAt:null};
}
export function planVisualEdit(manifest,{layerId,operation}){
 assert(manifest?.schema===VISUAL_DNA_SCHEMA,"Invalid manifest");
 const layer=manifest.layers.find(l=>l.id===layerId);
 if(!layer)return {status:"NOT_FOUND",reason:"No matching layer"};
 if(layer.stability==="CORE")return {status:"HOLD",reason:"LOCKED_CONTRACT_REOPEN required"};
 if(!["color","glow","motion","depth","replace-source","rename"].includes(operation))return {status:"REJECTED",reason:"Unsupported operation"};
 if(manifest.reviewState!=="APPROVED")return {status:"HOLD",reason:"Visual DNA is not approved"};
 return {status:"READY_FOR_AUTHORIZATION",target:{assetId:manifest.assetId,version:manifest.version,layerId,source:layer.source},operation,requires:["asset_ownership","entitlement","immutable_revision","render_validation"]};
}
