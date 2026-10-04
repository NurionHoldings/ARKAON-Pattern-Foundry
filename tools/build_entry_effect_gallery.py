"""Generate the portable, offline entrance effect comparison page."""
import json
from pathlib import Path
from apf.entry_effects import render_entry_effect, list_entry_effects


def build_gallery() -> str:
    effects = list_entry_effects()
    data = json.dumps(effects, ensure_ascii=False).replace('<', r'\u003c')
    template = json.dumps(render_entry_effect(title='더 아리랑 스토어',
                          subtitle='THE ARIRANG STORE'), ensure_ascii=False).replace('<', r'\u003c')
    return '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ARKAON 진입 효과 스튜디오</title>
<style>*{box-sizing:border-box}body{margin:0;background:#080f1c;color:#edf3ff;font-family:system-ui,sans-serif}header{padding:24px;max-width:1400px;margin:auto}h1{font-size:clamp(22px,4vw,36px)}.controls{display:flex;gap:16px;flex-wrap:wrap;align-items:end}label{display:grid;gap:8px;font-size:14px}input,select,button{font:inherit;border-radius:7px;padding:10px;background:#18263e;color:#edf3ff;border:1px solid #607595}input[type=color]{width:60px;height:44px;padding:4px}button{cursor:pointer}button:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid #c9a8ff;outline-offset:3px}iframe{width:100%;height:75svh;min-height:480px;border:0;display:block}p{color:#b8c8de;line-height:1.6}.hint{font-size:13px}</style>
<header><h1>ARKAON 진입 효과 스튜디오 · 9종</h1><p>효과를 선택하고 문구·색상·속도를 바꿔 재생하세요. 다운로드한 HTML은 독립 실행됩니다.</p><div class="controls">
<label>효과<select id="effect"></select></label><label>타이틀<input id="title" value="더 아리랑 스토어" maxlength="160"></label><label>보조문구<input id="subtitle" value="THE ARIRANG STORE" maxlength="160"></label><label>강조색<input id="accent" type="color" value="#ad79ff"></label><label>배경색<input id="background" type="color" value="#071522"></label><label>총 동작 시간<select id="duration"><option value="2">2초</option><option value="4" selected>4초</option><option value="6">6초</option></select></label><button id="play">다시 재생</button><button id="download">HTML 다운로드</button></div><p id="description" aria-live="polite"></p><p class="hint">기존 세 문구 적층 예제는 arirang-cinematic-gate.html에서 확인하세요. 시작 버튼 이후 플랫폼 영역은 서비스 연결용 예시입니다.</p></header>
<iframe id="preview" title="선택한 진입 효과 미리보기" sandbox="allow-scripts"></iframe>
<script>
const effects=__PAYLOAD__, template=__TEMPLATE__, get=id=>document.getElementById(id);let output='';
effects.forEach(e=>{const o=document.createElement('option');o.value=e.id;o.textContent=e.name;get('effect').append(o);});
function render(){const e=effects.find(e=>e.id===get('effect').value);const doc=new DOMParser().parseFromString(template,'text/html');doc.querySelector('.apf-gate').dataset.effect=e.id;const title=get('title').value.trim()||'ARKAON',subtitle=get('subtitle').value.trim()||'당신의 아이디어가 현실이 되는 순간';const h=doc.querySelector('.apf-title');h.textContent='';if(e.id==='arkaon-stagger-rise'){const wrapper=doc.createElement('span');wrapper.setAttribute('aria-label',title);const chars=typeof Intl.Segmenter==='function'?[...new Intl.Segmenter('ko',{granularity:'grapheme'}).segment(title)].map(x=>x.segment):Array.from(title);chars.forEach((char,i)=>{const span=doc.createElement('span');span.className='apf-char';span.setAttribute('aria-hidden','true');span.style.setProperty('--apf-progress',String(i/Math.max(1,chars.length-1)));span.textContent=char;wrapper.append(span);});h.append(wrapper);}else{h.textContent=title;}doc.querySelector('.apf-subtitle').textContent=subtitle;doc.documentElement.style.setProperty('--apf-accent',get('accent').value);doc.documentElement.style.setProperty('--apf-background',get('background').value);doc.documentElement.style.setProperty('--apf-duration',get('duration').value+'s');output='<!doctype html>'+doc.documentElement.outerHTML;get('preview').srcdoc=output;get('description').textContent=e.description+' · 호출 이름: '+e.id;}
get('play').addEventListener('click',render);['effect','accent','background','duration'].forEach(id=>get(id).addEventListener('change',render));get('download').addEventListener('click',()=>{render();const url=URL.createObjectURL(new Blob([output],{type:'text/html;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=get('effect').value+'.html';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});render();
</script></html>'''.replace('__PAYLOAD__', data).replace('__TEMPLATE__', template)


if __name__ == '__main__':
    path = Path(__file__).resolve().parents[1] / 'examples' / 'entry-effects-studio.html'
    path.write_text(build_gallery(), encoding='utf-8')
    print(path)
