# 63. 분석 대상 애매 시 cross-platform 연속 분석

- 명세 ID: APF-ANALYSIS-TARGET-RESOLUTION-001
- 상태: IMPLEMENTED / PROPOSE_ONLY

## 배경

아르카온이 **분석 대상을 정하기 애매한** 경우, 사용자가 **마지막으로 요청한 사이트**에서 찾고자 했던 **기능(intent·capability token)** 을 기준으로 **아직 분석·기록되지 않은 다른 플랫폼**을 순차적으로 분석하도록 한다.

중복 분석은 `state/analysis-target-resolution/analysis-ledger.jsonl` 로 차단한다.

## 애매함(ambiguity) 판정

| 코드 | 조건 |
|------|------|
| `NO_ENABLED_PLATFORMS` | `platforms.json` enabled 0건 |
| `LAST_REQUEST_NOT_IN_REGISTRY` | 마지막 사용자 사이트가 registered platform이 아님 (Wave 1 외부 학습 대상 등) |
| `ALL_ENABLED_PATHS_MISSING` | enabled 전부 workspace path 없음 |
| `ALL_PLATFORMS_BLOCKED` | 이번 run platform analysis 전부 `BLOCKED` |

## 마지막 사용자 사이트 기록

1. `inbox/operator-decision/*.json` — `platform_id`가 `knowledge/landing-intents` 와 일치하는 최신 패킷
2. `state/analysis-target-resolution/last-user-site-request.json` — 영속 기록

찾고자 했던 기능 토큰은 landing intent seed에서 추출:

- `landing-pattern:*` — `learning_focus.priority_patterns`
- `copy-angle:*` — `learning_focus.copy_angle_tags`
- `landing-signal:*` — `landing_intent.signal`
- `evolution-domain:*` — `evolution_domain_refs`

## cross-platform 라우팅

```text
AMBIGUOUS?
  → load last user site + sought tokens
  → list landing-intent platforms (exclude last site + registered owned)
  → skip ledger (platform, token) already analyzed
  → skip tokens already present in external inventory
  → emit research inbox (max N targets/run)
  → append ledger entries
```

## 권한 경계

| 허용 | 금지 |
|------|------|
| research inbox `CROSS_PLATFORM_ANALYSIS_CONTINUATION` | automatic implement |
| structural capability token 기준 라우팅 | competitor verbatim 저장 |
| ledger 기반 dedup | production change |

## 모듈

| 구성 | 경로 |
|------|------|
| 정책 | `config/arkaon-analysis-target-resolution.json` |
| 엔진 | `src/apf/analysis_target_resolution.py` |
| bridge | `src/apf/analysis_target_resolution_bridge.py` |
| orchestrator hook | `central_orchestrator._run_analysis_target_resolution` |
| 상태 | `state/analysis-target-resolution/` |

## orchestrator 위치

platform loop **직후**, run report 작성 **직전** — inbox capacity gate 적용.
