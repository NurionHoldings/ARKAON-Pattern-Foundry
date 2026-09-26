# 60. 무제한 학습 축적·엔진 성능

- 명세 ID: APF-ACCUMULATION-001
- 상태: IMPLEMENTED

## 원칙

아르카온의 **학습 능력이 향상될수록** 인위적인 용량·성능 상한을 두지 않고,
지식·자산·리포트·inbox 연구 패킷이 **끊임없이 축적**되도록 한다.

## 무제한 (accumulation / engine)

| 영역 | 이전 | 현재 |
|------|------|------|
| inbox 패킷 / run | 32 cap | **null = 무제한** |
| 플랫폼 / run | 8 cap | **null = 전체 enabled** |
| 플랫폼 파일 스캔 | 5000 cap | **null = 전체** |
| 분석 타임아웃 | 120s | **null = 무제한** |
| 학습 failure family | 3 cap | **null = 무제한** |
| curriculum batch | 고정 max | **null = 후보 전체** |
| SNS driver ranking | top 12 | **null = 전체** |
| 플랫폼 분석 | 순차 | **병렬 (기본)** |

설정:

- `config/arkaon-accumulation-policy.json` — 학습 메모리·curriculum·recall
- `config/resource-limits.json` (v2) — 오케스트레이터 처리량

## 안전 한도 (유지)

학습 **축적**과 무관한 **안전·보안** 한도만 남긴다:

- HTTP **요청당** `max_response_bytes` (collector, SNS watch)
- device auth TTL (map-ops)
- symlink escape, PII/secrets/credentials 거부
- `shared-policy` operational data 격리
- 승인 전 자동 배포·Intent 변경 금지

## 파이프라인

```text
config/arkaon-accumulation-policy.json
  → LearningMemory.from_foundry() — failure family 무제한
  → plan_curriculum(max_items=None) — 전 후보 수집

config/resource-limits.json (v2, unbounded)
  → CentralOrchestrator — inbox/파일/타임아웃/병렬 무제한
  → state/*, knowledge/* — dated snapshot 누적 (prune 없음)
```

## bounded로 되돌리기

운영자가 명시적으로 `accumulation_mode: "bounded"` 및 양수 limit을 설정하면
v1 스타일 상한을 복원할 수 있다.
