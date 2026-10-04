# 아르카온 시네마틱 게이트

고유 이름: `arkaon-cinematic-gate`. 한국어 별칭: `시네마틱 게이트`, `아르카온 시네마틱 게이트`.
코드생성 토큰: `entry-effect:arkaon-cinematic-gate`.

첨부파일은 확장자와 달리 654×368 단일 PNG다. 사용자 설명대로 중앙에서 좌우로 펼쳐지는
타이틀을 CSS로 구현했다. 짙은 청색 배경, 수평 보라색 광선, 금속성 글자와 자리잡기 효과를 제공한다.
원본 영상의 타이밍은 확인할 수 없으므로 2.3초 펼침은 구현 기본값이다. 음악은 포함하지 않는다.

## 문구만 바꾸어 적용

```python
from apf.entry_effects import render_entry_effect
page = render_entry_effect("시네마틱 게이트", title="원하는 문구", subtitle="원하는 보조문구")
```

반환값은 의존성 없는 완전한 HTML이다. 기본 타이틀은 ARKAON.
공동제작 `pattern_token`으로도 진입 페이지를 생성한다. 생성되는 섹션 파일은 완전한 페이지이므로
별도 진입 페이지 또는 iframe으로 사용한다. 실제 플랫폼은 `.apf-platform` 내부에 넣는다.
시작/건너뛰기는 플랫폼을 표시하고 `arkaon:entered` 이벤트를 발생시킨다.
해당 이벤트에서 실제 서비스 라우터를 연결할 수 있다. 운영 URL은 추정하지 않는다.

모바일 크기 조절, 건너뛰기, 다시 보기, 키보드 포커스, 중복 클릭 방지, 전환 종료 대체 타이머,
`prefers-reduced-motion`을 지원한다. 문구는 HTML 이스케이프 처리한다.
CSP가 인라인 스크립트를 차단하는 사이트는 CSS/JS를 별도 파일로 분리한다.
이 변경은 엔진에 재사용 기능을 추가하며 기존 서비스 홈 배포를 변경하지 않는다.

공동제작 섹션 옵션 예:
```json
{"section_id":"intro","purpose":"스토어 진입","pattern_token":"entry-effect:arkaon-cinematic-gate","entry_effect":{"title":"더 아리랑 스토어","subtitle":"THE ARIRANG STORE"}}
```
테스트 예제: `examples/arirang-cinematic-gate.html`을 브라우저로 열면 즉시 재생된다.

## 순차 레이어 모드: 중앙 적층 후 이동·돌출

`title_parts=["더", "아리랑", "스토어"]`는 최종 읽기 순서인 왼쪽·중앙·오른쪽이다.
시작 깊이는 더(앞), 스토어(중간), 아리랑(뒤)이며 모두 중앙에 겹쳐 놓는다.
0.4초부터 더가 왼쪽으로 이동, 1.6초부터 스토어가 오른쪽으로 이동,
2.8초부터 아리랑 세 글자 전체가 금색으로 변화하며 앞으로 돌출된다.
각 단계는 1.2초이며 마지막 상태를 유지한다. 다시 보기는 전체 순서를 초기화한다.
동작 감소 설정에서는 즉시 최종 배치를 보여준다.

```python
page = render_entry_effect("시네마틱 게이트",
    title_parts=["더", "아리랑", "스토어"], subtitle="THE ARIRANG STORE")
```

공동제작의 `entry_effect` 옵션에도 `"title_parts":["더","아리랑","스토어"]`를 지정한다.
각 문구는 최대 24자로 제한되며 긴 문구는 적용 화면 크기에 맞게 조정한다.
`title_parts` 생략 시 기존 단일 타이틀 좌우 펼침을 유지한다.
