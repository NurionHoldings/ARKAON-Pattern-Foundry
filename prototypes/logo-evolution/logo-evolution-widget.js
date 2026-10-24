/**
 * ARKAON Logo Evolution Engine — framework-neutral UI prototype.
 * Embed as <script type="module" src="/.../logo-evolution-widget.js"></script>
 * and <arkaon-logo-evolution logo-src="/path/to/approved-logo.png"></arkaon-logo-evolution>.
 * This file never uploads logos or charges customers. Preview is illustrative CSS only.
 */
const LEVELS=[
 {name:"원본",effects:[]},
 {name:"색상 활성화",effects:["color_shift","outline_neon"]},
 {name:"빛과 움직임",effects:["color_shift","outline_neon","text_stagger","specular_sweep","trace_current"]},
 {name:"입체적 연출",effects:["color_shift","outline_neon","text_stagger","specular_sweep","trace_current","depth_pop","radial_wave","material_reflection"]},
 {name:"시네마틱",effects:["color_shift","outline_neon","text_stagger","specular_sweep","trace_current","depth_pop","radial_wave","material_reflection","cinematic_timeline"]}
];
const SUPPORT={
 text:["color_shift","text_stagger","specular_sweep","depth_pop"],
 geometric:["color_shift","outline_neon","trace_current","radial_wave"],
 metallic:["color_shift","specular_sweep","material_reflection","outline_neon"],
 character:["color_shift","specular_sweep"],
 symbol:["color_shift","outline_neon","radial_wave","depth_pop"]
};
export function resolveLogoEvolution({level=1,logoType="symbol",intensity="balanced"}={}){
 const l=Math.max(1,Math.min(5,Math.round(Number(level)||1)));
 const type=Object.hasOwn(SUPPORT,logoType)?logoType:"symbol";
 const allowed=SUPPORT[type];
 return {schemaVersion:1,level:l,logoType:type,intensity:["natural","balanced","vivid"].includes(intensity)?intensity:"balanced",supportedEffects:LEVELS[l-1].effects.filter(x=>allowed.includes(x)),omittedEffects:LEVELS[l-1].effects.filter(x=>!allowed.includes(x)),previewOnly:true};
}
class ArkaonLogoEvolution extends HTMLElement{
 connectedCallback(){
  if(this.shadowRoot)return;
  const root=this.attachShadow({mode:"open"});
  root.innerHTML=`<style>
   :host{display:block;font:15px/1.5 system-ui,sans-serif;color:#e7edf7}
   .panel{background:#101a2b;border:1px solid #35445d;border-radius:18px;padding:20px;max-width:600px}
   .preview{display:grid;place-items:center;min-height:190px;background:radial-gradient(circle,#1c2b48,#0b1120);border-radius:12px;overflow:hidden;margin:12px 0}
   .art{max-width:70%;max-height:150px;object-fit:contain;transition:filter .3s,transform .3s}
   .placeholder{font-weight:800;letter-spacing:.12em;font-size:2rem}
   .glow{filter:drop-shadow(0 0 8px #45bfffa0)}
   .motion{animation:arkaonPop 2.7s ease-in-out infinite}
   .vivid{filter:drop-shadow(0 0 14px #61d8ff) saturate(1.4)}
   @keyframes arkaonPop{0%,100%{transform:scale(1)}30%{transform:scale(1.1)}}
   @media(prefers-reduced-motion:reduce){.motion{animation:none!important}}
   label{display:block;margin:10px 0 4px}input[type=range]{width:100%;accent-color:#59c5ff}
   select,button{background:#233653;color:#fff;border:1px solid #587094;border-radius:8px;padding:8px}
   button{cursor:pointer;margin-top:12px}button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid #fff;outline-offset:3px}
   .hint{color:#aebed3;font-size:13px}.tags{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0}.tag{background:#203b56;padding:3px 8px;border-radius:12px;font-size:12px}
  </style>
  <section class="panel" aria-label="ARKAON 로고 고도화">
   <strong>ARKAON · 로고 진화 엔진</strong>
   <div class="preview" aria-label="로고 효과 예시"><span class="placeholder art" id="art">MY LOGO</span></div>
   <label for="level">추가 구현 레벨 <strong id="levelName">1 · 원본</strong></label>
   <input id="level" type="range" min="1" max="5" step="1" value="1" aria-label="로고 구현 레벨">
   <label for="type">로고 유형</label><select id="type">
    <option value="symbol">심볼</option><option value="text">텍스트</option><option value="geometric">기하학</option><option value="metallic">금속</option><option value="character">캐릭터</option>
   </select>
   <label for="intensity">연출 성향</label><select id="intensity">
    <option value="natural">자연스럽게</option><option value="balanced" selected>균형</option><option value="vivid">강렬하게</option>
   </select>
   <div id="effects" class="tags" aria-live="polite"></div>
   <p class="hint" id="notice">이 화면은 시각적 예시입니다. 실제 렌더링이 아닙니다.</p>
   <button id="copy" type="button">설정 JSON 복사</button>
  </section>`;
  const $=id=>root.getElementById(id);
  const src=this.getAttribute("logo-src");
  if(src){const img=document.createElement("img");img.alt="승인된 원본 로고";img.className="art";img.src=src;$("art").replaceWith(img);img.id="art";}
  const update=()=>{
   const config=resolveLogoEvolution({level:$("level").value,logoType:$("type").value,intensity:$("intensity").value});
   $("levelName").textContent=`${config.level} · ${LEVELS[config.level-1].name}`;
   const art=$("art");
   art.className="art"+(config.level>=2?" glow":"")+(config.level>=4?" motion":"")+(config.intensity==="vivid"&&config.level>=2?" vivid":"");
   $("effects").replaceChildren(...config.supportedEffects.map(e=>{const s=document.createElement("span");s.className="tag";s.textContent=e;return s;}));
   $("notice").textContent=`미리보기 예시 · 적용 가능 ${config.supportedEffects.length}개 · 미지원 ${config.omittedEffects.length}개 (렌더 엔진 연결 전)`;
   this.dispatchEvent(new CustomEvent("logo-evolution-change",{detail:config,bubbles:true,composed:true}));
   this._config=config;
  };
  ["level","type","intensity"].forEach(id=>$(id).addEventListener("input",update));
  $("copy").addEventListener("click",async()=>{
   try{await navigator.clipboard.writeText(JSON.stringify(this._config,null,2));$("copy").textContent="복사 완료";}
   catch{$("copy").textContent="복사 불가 — 보안 연결 확인";}
  });
  update();
 }
}
if(!customElements.get("arkaon-logo-evolution"))customElements.define("arkaon-logo-evolution",ArkaonLogoEvolution);
