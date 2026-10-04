"""Original entrance presets derived from documented web animation primitives."""

PRESETS = {
    'arkaon-cinematic-gate': ('아르카온 시네마틱 게이트', '중앙 펼침 / 세 문구 순차 이동·돌출', 'apf-title-unfold'),
    'arkaon-iris-reveal': ('아르카온 아이리스 오픈', '중앙 원형 마스크가 넓어지는 진입', 'apf-iris'),
    'arkaon-curtain-open': ('아르카온 커튼 오픈', '좌우 커튼이 열리는 무대형 진입', 'apf-curtain-title'),
    'arkaon-stagger-rise': ('아르카온 순차 타이포', '글자가 차례로 올라와 정렬', 'apf-stagger'),
    'arkaon-focus-reveal': ('아르카온 포커스 리빌', '흐릿한 글자가 선명하게 자리잡음', 'apf-focus'),
    'arkaon-neon-trace': ('아르카온 네온 트레이스', '윤곽에서 발광 타이틀로 전환', 'apf-neon'),
    'arkaon-perspective-flip': ('아르카온 입체 플립', '원근 회전으로 타이틀 등장', 'apf-flip'),
    'arkaon-orbit-halo': ('아르카온 오비트 헤일로', '빛의 궤도가 타이틀 주위에 정착', 'apf-orbit-title'),
    'arkaon-scan-reveal': ('아르카온 스캔 리빌', '빛이 위에서 아래로 문구를 스캔', 'apf-scan'),
}

PRESET_CSS = r'''
.apf-gate{background:radial-gradient(ellipse at center,#263b58,var(--apf-background) 75%)}
.apf-beam{background:linear-gradient(90deg,transparent,var(--apf-accent),#fff,var(--apf-accent),transparent);box-shadow:0 0 18px var(--apf-accent)}
.apf-title{animation-duration:var(--apf-duration)}
.apf-word{animation-duration:calc(var(--apf-duration)*.3)}
.apf-word-left{animation-delay:calc(var(--apf-duration)*.1)}
.apf-word-right{animation-delay:calc(var(--apf-duration)*.4)}
.apf-word-center{animation-delay:calc(var(--apf-duration)*.7)}
.apf-gate[data-effect="arkaon-iris-reveal"] .apf-content{animation:apf-iris var(--apf-duration) ease both}
.apf-gate[data-effect="arkaon-iris-reveal"] .apf-title{animation:none}
@keyframes apf-iris{from{clip-path:circle(0% at 50% 50%)}to{clip-path:circle(100% at 50% 50%)}}
.apf-gate[data-effect="arkaon-curtain-open"]:after{content:"";position:absolute;inset:0;z-index:2;pointer-events:none;background:linear-gradient(90deg,var(--apf-background),#314061,var(--apf-background));animation:apf-curtains var(--apf-duration) ease-in-out both}
.apf-gate[data-effect="arkaon-curtain-open"] .apf-title{animation-name:apf-curtain-title}
.apf-skip{z-index:5}
@keyframes apf-curtains{0%,12%{clip-path:polygon(0 0,100% 0,100% 100%,0 100%,0 0,50% 0,50% 100%,50% 100%,50% 0)}100%{clip-path:polygon(0 0,100% 0,100% 100%,0 100%,0 0,0 0,0 100%,100% 100%,100% 0)}}
@keyframes apf-curtain-title{from{opacity:0;transform:scale(.95)}to{opacity:1;transform:scale(1)}}
.apf-gate[data-effect="arkaon-stagger-rise"] .apf-title{animation:none;background:none;color:#eee3d4;filter:none}
.apf-char{display:inline-block;white-space:pre;animation:apf-stagger calc(var(--apf-duration)*.4) cubic-bezier(.2,1,.3,1) both;animation-delay:calc(var(--apf-duration)*.6*var(--apf-progress))}
@keyframes apf-stagger{from{opacity:0;transform:translateY(1em) rotateX(-65deg)}to{opacity:1;transform:none}}
.apf-gate[data-effect="arkaon-focus-reveal"] .apf-title{animation-name:apf-focus}
@keyframes apf-focus{from{opacity:0;filter:blur(18px);transform:scale(1.12)}to{opacity:1;filter:blur(0);transform:scale(1)}}
.apf-gate[data-effect="arkaon-neon-trace"] .apf-title{background:none;animation-name:apf-neon;-webkit-text-stroke:1px var(--apf-accent)}
@keyframes apf-neon{0%{color:transparent;opacity:0;text-shadow:none}40%{color:transparent;opacity:1;text-shadow:0 0 5px var(--apf-accent)}100%{color:#f4eeff;opacity:1;text-shadow:0 0 12px var(--apf-accent),0 0 28px var(--apf-accent)}}
.apf-gate[data-effect="arkaon-perspective-flip"] .apf-title{animation-name:apf-flip}
@keyframes apf-flip{from{opacity:0;transform:perspective(900px) rotateY(-80deg) translateZ(-100px)}to{opacity:1;transform:perspective(900px) rotateY(0) translateZ(0)}}
.apf-gate[data-effect="arkaon-orbit-halo"]:after{content:"";position:absolute;width:min(70vw,600px);aspect-ratio:1;border:2px solid var(--apf-accent);border-radius:50%;box-shadow:0 0 30px var(--apf-accent);pointer-events:none;animation:apf-orbit var(--apf-duration) ease-out both}
.apf-gate[data-effect="arkaon-orbit-halo"] .apf-title{animation-name:apf-orbit-title}
@keyframes apf-orbit{from{opacity:0;transform:perspective(800px) rotateX(75deg) rotateY(70deg) scale(.4)}to{opacity:.3;transform:perspective(800px) rotateX(55deg) rotateY(-15deg) scale(1)}}
@keyframes apf-orbit-title{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:none}}
.apf-gate[data-effect="arkaon-scan-reveal"] .apf-title{animation-name:apf-scan}
.apf-gate[data-effect="arkaon-scan-reveal"] .apf-beam{animation:apf-scan-beam var(--apf-duration) linear both;transform:none}
@keyframes apf-scan{from{clip-path:inset(0 0 100% 0)}to{clip-path:inset(0 0 0 0)}}
@keyframes apf-scan-beam{0%{top:25%;opacity:0}15%{opacity:1}85%{opacity:1}100%{top:75%;opacity:0}}
@media(prefers-reduced-motion:reduce){.apf-content,.apf-title,.apf-char,.apf-word,.apf-gate:after{animation:none!important;opacity:1;clip-path:none;transform:none;filter:none}.apf-gate[data-effect="arkaon-curtain-open"]:after{display:none}.apf-gate[data-effect="arkaon-neon-trace"] .apf-title{color:#f4eeff}.apf-gate[data-effect="arkaon-orbit-halo"]:after{opacity:.3}}
'''


def resolve_effect(name: str) -> str:
    if name == '시네마틱 게이트':
        return 'arkaon-cinematic-gate'
    for effect_id, (label, _, _) in PRESETS.items():
        if name in (effect_id, label, label.removeprefix('아르카온 ')):
            return effect_id
    raise ValueError(f'Unknown entry effect: {name}')


def is_entry_effect_token(token: str) -> bool:
    return token.startswith('entry-effect:') and token.removeprefix('entry-effect:') in PRESETS


def list_entry_effects() -> list[dict[str, str]]:
    return [{'id': key, 'name': value[0], 'description': value[1],
             'pattern_token': 'entry-effect:' + key} for key, value in PRESETS.items()]
