# ARKAON 진입 효과 라이브러리 v1

## 효과 이름으로 요청·생성

| ID | 한국어 이름 | 동작 |
|---|---|---|
| arkaon-cinematic-gate | 시네마틱 게이트 | 중앙 펼침 / 세 문구 적층·순차 이동·돌출 |
| arkaon-iris-reveal | 아이리스 오픈 | 중앙 원형 마스크 확대 |
| arkaon-curtain-open | 커튼 오픈 | 좌우 커튼 개방 |
| arkaon-stagger-rise | 순차 타이포 | 문자별 순차 상승 |
| arkaon-focus-reveal | 포커스 리빌 | 흐림에서 선명한 타이틀 |
| arkaon-neon-trace | 네온 트레이스 | 윤곽에서 발광 타이틀 |
| arkaon-perspective-flip | 입체 플립 | 원근 회전 등장 |
| arkaon-orbit-halo | 오비트 헤일로 | 빛의 궤도 정착 |
| arkaon-scan-reveal | 스캔 리빌 | 위에서 아래로 빛 스캔 |

요청 예: “더 아리랑 스토어의 진입에 아이리스 오픈을 적용하고, 강조색을 금색으로 해줘.”
`list_entry_effects()`로 ID·이름·설명·코드생성 토큰을 조회한다.
`config/arkaon-entry-effects.json`은 동일 목록의 검색용 스냅샷이다.

```python
from apf.entry_effects import render_entry_effect
page = render_entry_effect('아이리스 오픈', title='더 아리랑 스토어',
    subtitle='THE ARIRANG STORE', accent='#e9c477', background='#101725', duration=4)
```

CLI: `PYTHONPATH=src python -m apf.entry_effects --effect '입체 플립' --title '더 아리랑 스토어' --output preview.html`
목록: `PYTHONPATH=src python -m apf.entry_effects --list`

공동제작 섹션 예:
```json
{"section_id":"intro","purpose":"브랜드 진입","pattern_token":"entry-effect:arkaon-iris-reveal","entry_effect":{"title":"더 아리랑 스토어","subtitle":"THE ARIRANG STORE","accent":"#e9c477","background":"#101725","duration":4}}
```

문구 길이는 1–160자, 색상은 #RRGGBB, 동작 시간은 0.5–8초다.
단일 타이틀에서 기본 duration은 4초다. 세 문구 적층은 시네마틱 게이트에만 적용한다.
HTML은 독립 페이지이며 서비스에서 별도 진입 페이지나 iframe으로 활용한다.
`arkaon:entered` 이벤트의 `detail.effect`로 선택 효과를 확인하고 서비스 라우터에 연결한다.
기존 서버 API, 운영 홈, 결제 흐름 또는 자동 배포 설정은 변경하지 않는다.

## 비교·문구 수정·다운로드

`examples/entry-effects-studio.html`을 열어 9종을 선택한다. 문구, 보조문구,
강조색, 배경색, 속도를 바꿔 다시 재생하고 결과 HTML을 다운로드할 수 있다.
외부 CDN, 폰트, 이미지, 음원, 추적 또는 네트워크 호출 없이 실행한다.
재생성: `PYTHONPATH=src python tools/build_entry_effect_gallery.py`.
세 문구 적층 예제는 `examples/arirang-cinematic-gate.html`에 있다.

## 웹 조사 근거 (2026-10-04)

기술 원리를 참고해 자체 CSS/JS를 작성했다. 유료 컴포넌트나 사이트의 코드·이미지를 복제하지 않았다.

- [MDN clip-path](https://developer.mozilla.org/en-US/docs/Web/CSS/clip-path): 원형 마스크, 커튼, 스캔.
- [MDN perspective](https://developer.mozilla.org/en-US/docs/Web/CSS/perspective): 원근 회전, 글자 돌출, 궤도.
- [Motion text animation](https://motion.dev/docs/text-animation): 글자 분할과 순차 등장 원리. Motion 런타임 의존성 없음.
- [MDN prefers-reduced-motion](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion): OS 동작 감소 설정 대응.
- [MDN View Transition API](https://developer.mozilla.org/en-US/docs/Web/API/View_Transition_API): 후속 실제 페이지 전환 확장 참고. 이번 버전은 이 API를 요구하거나 구현하지 않는다.

## 검증 범위와 적용 주의

이름 기반 렌더·입력 검증·HTML 이스케이프·실제 공동제작 코드생성 경로를 테스트한다.
동작 감소 설정은 즉시 최종 상태를 표시하고 커튼을 제거한다. 시작·건너뛰기·다시 보기,
포커스 이동을 유지한다. 타이틀 길이와 서비스 폰트에 따라 모바일 글자 크기를 조정한다.
CSS clip-path/3D에 대한 최종 브라우저 시각 확인은 별도로 필요하다.
CSP가 인라인 CSS/JS를 차단하면 외부 파일로 분리한다.

검증 기록: 관련 pytest 34 PASS. jsdom에서 9종 선택, 문구 수정·이스케이프, 효과 ID 이벤트,
시작/건너뛰기/다시 보기와 동작 감소 분기를 확인했다. DOM 검사는 브라우저 렌더 검사를 대체하지 않는다.
재실행: jsdom이 설치된 환경에서 `node tests/entry_effect_dom_check.cjs`.

## 문구별 개별 효과와 폰트

`text_segments`에 문구별 설정을 지정한다. 최대 12개이며 각 문구는 1–80자다.

- 등장 `enter`: `none`, `fade-in`, `rise`, `zoom-in`, `flip-in`
- 빛 `glow`: `none`, `glow`(지속 발광), `pulse`(맥동), `shine`(빛 훑기)
- 퇴장 `exit`: `none`, `fade-out`, `sink`, `zoom-out`
- 시간(초): `delay`, `duration`, `hold`, `exit_duration`; 각 값 0–30
- 색상: `color`, `glow_color`; #RRGGBB
- 서체: `font`, `font_family`; 굵기 `weight` 100–900

빛 맥동·훑기는 3회 반복 후 정착한다. 퇴장 시작은 delay+duration+hold이다.
동작 감소 설정에서는 퇴장하지 않고 문구를 읽을 수 있게 유지한다.

```python
page = render_entry_effect('시네마틱 게이트', font='gothic',
    text_segments=[
        {'text':'더', 'enter':'fade-in', 'glow':'glow'},
        {'text':'아리랑', 'delay':1, 'enter':'zoom-in', 'glow':'shine', 'font':'serif'},
        {'text':'스토어', 'delay':2, 'enter':'rise', 'exit':'fade-out', 'hold':3},
    ])
```

중앙 적층과 결합하려면 `title_parts`와 동일한 3개 문구를 같은 순서로 지정한다.
외부 문구 이동과 내부 빛·등장·퇴장은 서로 다른 요소에 적용되어 transform 충돌을 피한다.
API, CLI(`--font`, `--font-family`, `--text-segments 파일.json`), 공동제작
`entry_effect`에서도 같은 옵션을 받는다. 예제는 `examples/arirang-text-effects.html`.

서체 선택: system(시스템), gothic(맑은 고딕), serif(바탕·명조), gulim(굴림),
arial, georgia, mono(고정폭). 해당 서체가 기기에 없으면 지정된 대체 서체로 표시된다.
`font_family='Pretendard'`처럼 설치된 서체를 대입할 수 있다.
스튜디오에서는 유효한 WOFF2 파일(2MB 이하)을 선택해 문구 전체에 적용하고
다운로드 HTML에 폰트를 포함할 수 있다. 글자별 폰트 선택은 업로드 폰트를 해제한 상태에서 사용한다.
폰트 파일 대입은 스튜디오 기능이며 서버 렌더 API는 서체 이름/스택을 받는다.

## 통합 점검

기존 PR의 import 순서 lint 오류를 수정했다. config 목록은 아르카온 자동 기능 탐색이
읽는 객체 형태(schema_version/enabled/effects)로 정리했다. 전체 회귀 858 PASS / 13 SKIP
(별도 DB가 필요한 테스트 포함). 관련 효과 테스트 49 PASS 및 DOM 동작 검사 통과.
