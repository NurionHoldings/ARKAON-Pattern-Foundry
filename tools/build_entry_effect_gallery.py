"""Generate the portable, offline entrance effect comparison page."""
import json
from pathlib import Path

from apf.entry_effects import list_entry_effects, render_entry_effect
from apf.text_effects import FONTS


def build_gallery() -> str:
    effects = list_entry_effects()
    data = json.dumps(effects, ensure_ascii=False).replace('<', r'\u003c')
    template = json.dumps(render_entry_effect(title='더 아리랑 스토어',
                          subtitle='THE ARIRANG STORE'), ensure_ascii=False).replace('<', r'\u003c')
    script = Path(__file__).with_name('entry_effect_studio.js').read_text(encoding='utf-8')
    script = script.replace('__PAYLOAD__', data).replace('__TEMPLATE__', template).replace('__FONTS__', json.dumps(FONTS, ensure_ascii=False))
    return '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ARKAON 진입 효과 스튜디오</title>
<style>*{box-sizing:border-box}body{margin:0;background:#080f1c;color:#edf3ff;font-family:system-ui,sans-serif}header{padding:24px;max-width:1400px;margin:auto}h1{font-size:clamp(22px,4vw,36px)}.controls{display:flex;gap:16px;flex-wrap:wrap;align-items:end}label{display:grid;gap:8px;font-size:14px}input,select,button{font:inherit;border-radius:7px;padding:10px;background:#18263e;color:#edf3ff;border:1px solid #607595}input[type=color]{width:60px;height:44px;padding:4px}button{cursor:pointer}button:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid #c9a8ff;outline-offset:3px}iframe{width:100%;height:75svh;min-height:480px;border:0;display:block}p{color:#b8c8de;line-height:1.6}.hint{font-size:13px}.segment-row{display:flex;flex-wrap:wrap;gap:10px;padding:15px 0;border-bottom:1px solid #42506a}.segment-row input[type=number]{width:85px}#error{color:#ffd99b}.toggle{display:flex;align-items:center;gap:8px;margin:14px 0}.toggle input{width:auto}[hidden]{display:none!important}</style>
<header><h1>ARKAON 진입 효과 스튜디오 · 9종</h1><p>효과를 선택하고 문구·색상·속도를 바꿔 재생하세요. 다운로드한 HTML은 독립 실행됩니다.</p><div class="controls">
<label>효과<select id="effect"></select></label><label>타이틀<input id="title" value="더 아리랑 스토어" maxlength="160"></label><label>보조문구<input id="subtitle" value="THE ARIRANG STORE" maxlength="160"></label><label>강조색<input id="accent" type="color" value="#ad79ff"></label><label>배경색<input id="background" type="color" value="#071522"></label><label>전체 서체<select id="font"></select></label><label>설치된 폰트 이름<input id="font-family" placeholder="예: Pretendard" maxlength="80"></label><label>폰트 파일 대입<input id="font-file" type="file" accept=".woff2"></label><label>총 동작 시간<select id="duration"><option value="2">2초</option><option value="4" selected>4초</option><option value="6">6초</option></select></label><button id="play">다시 재생</button><button id="download">HTML 다운로드</button></div><label class="toggle"><input id="individual" type="checkbox">문구별 개별 효과 사용</label><label class="toggle"><input id="layered" type="checkbox">세 문구 중앙 적층·순차 이동도 함께 적용</label><div id="segment-editor" hidden><div id="segments"></div><button id="add-segment" type="button">문구 추가</button></div><p id="error" role="alert"></p><p id="description" aria-live="polite"></p><p class="hint">기존 세 문구 적층 예제는 arirang-cinematic-gate.html에서 확인하세요. 시작 버튼 이후 플랫폼 영역은 서비스 연결용 예시입니다.</p></header>
<iframe id="preview" title="선택한 진입 효과 미리보기" sandbox="allow-scripts"></iframe>
<script>
__SCRIPT__
</script></html>'''.replace('__SCRIPT__', script)


if __name__ == '__main__':
    path = Path(__file__).resolve().parents[1] / 'examples' / 'entry-effects-studio.html'
    path.write_text(build_gallery(), encoding='utf-8')
    print(path)
