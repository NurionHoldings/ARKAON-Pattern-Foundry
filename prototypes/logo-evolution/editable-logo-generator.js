import {registerGeneratedLogo,locateEditPoint} from "./generator-visual-dna-adapter.js";
const AXES=["WHY","WHO","VALUE","OUTCOME","JOURNEY","OBJECT","OWNER","INVARIANT","CONSTRAINT","RISK","SIGNAL","EVOLUTION"];
const esc=s=>s.replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&apos;");
const safeId=s=>s.replace(/[^a-zA-Z0-9_-]/g,"").slice(0,50)||"logo";
export function buildLogoSvg({brand="ARKAON",accent="#56c8ff"}={}){
 brand=String(brand).trim().slice(0,28);if(!brand)throw Error("Brand name required");
 if(!/^#[0-9a-fA-F]{6}$/.test(accent))throw Error("Invalid accent");
 const svg=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024"><g id="symbol01"><circle cx="512" cy="355" r="138" fill="none" stroke="${accent}" stroke-width="26"/><path d="M435 355L512 275L589 355L512 435Z" fill="${accent}"/></g><g id="brandText01"><text x="512" y="685" font-family="sans-serif" font-weight="700" font-size="76" text-anchor="middle" fill="#edf6ff" textLength="780" lengthAdjust="spacingAndGlyphs">${esc(brand)}</text></g></svg>`;
 return {svg,brand,accent};
}
export async function generateEditableLogo({brand,accent,assetId="demoLogo01",intentFingerprint="a".repeat(64)}={}){
 const {svg}=buildLogoSvg({brand,accent});
 const intentAxes=Object.fromEntries(AXES.map(a=>[a,[]]));
 intentAxes.WHY=["Brand identification"];intentAxes.WHO=["Asset owner"];intentAxes.OUTCOME=["Editable logo"];
 intentAxes.OBJECT=["Logo"];intentAxes.INVARIANT=["Preserve brand text"];intentAxes.EVOLUTION=["Animation"];
 const layers=[
  {id:"symbol01",kind:"symbol",label:"Symbol",stability:"CONFIGURABLE",bounds:{x:360,y:217,width:304,height:276},intentLinks:["OBJECT","EVOLUTION"],source:{type:"svg-node",ref:"symbol01"}},
  {id:"brandText01",kind:"text",label:"Brand text",stability:"CORE",bounds:{x:122,y:600,width:780,height:110},intentLinks:["INVARIANT","OUTCOME"],source:{type:"svg-node",ref:"brandText01"}}
 ];
 const sourceBlob=new Blob([svg],{type:"image/svg+xml"});
 const registration=await registerGeneratedLogo({assetId:safeId(assetId),sourceBlob,canvas:{width:1024,height:1024},layers,intentAxes,intentFingerprint});
 return {...registration,svg,brand,accent,locate:(id,operation)=>locateEditPoint(registration.manifest,id,operation)};
}
