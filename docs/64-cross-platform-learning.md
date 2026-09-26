# 64. Cross-platform 학습 폐루 (EXECUTE → LESSON)

- 명세 ID: APF-CROSS-PLATFORM-LEARNING-001
- 상태: IMPLEMENTED / PROPOSE_ONLY

## 배경

`analysis_target_resolution` (#63)은 **다음에 무엇을 볼지** 라우팅한다.  
본 모듈은 라우팅 **이후** 학습 폐루를 닫는다.

```text
EXECUTE  → HTTPS fetch 또는 landing-intent route 추론 → surface-observations
COMPARE  → source + target 공통 policy_route_refs vs sought tokens
ABSTRACT → knowledge/landing-structure-patterns/proposed/*.json
LESSON   → reflective case seed + eternian-review CROSS_PLATFORM_LESSON_SEED
```

## 권한 경계

| 허용 | 금지 |
|------|------|
| 공개 HTTPS structural fetch | verbatim copy 저장 |
| landing structure pattern **PROPOSED** | 30-pattern catalog 자동 추가 |
| eternian lesson seed | immutable lesson without operator |
| landing-intent route 추론 (fetch 불가 시) | production change |

## 설정

- `config/arkaon-cross-platform-learning.json`
- `platform_urls` — fetch 대상 URL (landing-intent `public_url` 보조)

## orchestrator

`_run_analysis_target_resolution` 직후 `_run_cross_platform_learning` 호출.

## 산출물

| 경로 | 내용 |
|------|------|
| `state/surface-observations/` | target platform fetch 결과 |
| `knowledge/landing-structure-patterns/proposed/` | cross-platform abstract pattern |
| `state/cross-platform-learning/latest.json` | run report |
| `inbox/eternian-review/*-xplat-lesson-*` | lesson seed (SYNTHETIC_SHADOWED) |

immutable `knowledge/reflective-lessons/` append는 eternian → operator 결정 후 (#049).
