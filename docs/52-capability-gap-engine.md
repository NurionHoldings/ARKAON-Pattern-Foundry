# 52. Capability Gap Engine (아르카온 핵심)

- 명세 ID: APF-CAP-GAP-001
- 상태: IMPLEMENTED / request-only

## 역할 (가장 중요한 기능)

```text
외부 접속·관측·검색
  → "다른 사이트/플랫폼에는 있는데 내 플랫폼에는 없다"
  → ARKAON이 스스로 격차를 인식
  → 필요한 조치를 inbox에 요청 (research / eternian-review / operator-decision)
```

자동 구현·배포·Intent 변경은 **하지 않는다**.

## 입력

| 소스 | 추출 |
|------|------|
| 등록 플랫폼 workspace | OpenAPI path, policy route (owned inventory) |
| `state/surface-observations/` | external structural tokens |
| `knowledge/landing-intents/` | landing-pattern tokens |

토큰 예: `api-surface:waitlist`, `landing-pattern:food-trust-block` — **원문·카피 없음**.

## 출력

- `state/capability-gap/*.json` — 격차 리포트
- `inbox/research/*-capability-gap-research.json`
- `inbox/eternian-review/*-capability-gap-eternian.json` (HIGH)
- `inbox/operator-decision/*-capability-gap-operator.json`

각 gap마다 `requested_actions` 3건: research 재확인, eternian 합성 검토, operator 우선순위.

## 구현

```text
src/apf/capability_gap.py
src/apf/capability_gap_bridge.py
config/arkaon-capability-gap.json
tests/test_capability_gap.py
```

오케스트레이터: 등록 플랫폼 분석 후 `_run_capability_gap`  
콘솔: `GET /v1/console/capability-gaps`

## 경계

- competitor verbatim storage 금지
- `automatic_implement_allowed` / `production_change_allowed` false
- gap = structural token diff; 사용자-facing 문장은 advisory `user_message` only

격차 inbox 패킷은 [53-mailbox-delivery-flow.md](53-mailbox-delivery-flow.md) 우편함으로 동기화되어
에테르니언/범 방문 → 사용자 전달 → 승인 → 이행 큐로 이어진다.
