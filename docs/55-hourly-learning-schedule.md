# 55. 시간별 주제 자율 학습·수집

- 명세 ID: APF-HOURLY-LEARN-001
- 상태: IMPLEMENTED / EXTERNAL_LEARNING_ONLY

## 목표

아르카온은 **로컬 시간 기준 매 시간(other 24 slots)** 마다 진화 도메인 주제를 정하고,
15분 주기 수집 런타임이 **그 시간의 주제에 맞는 소스만** 스스로 수집한다.

## 설정

| 파일 | 역할 |
|------|------|
| `config/arkaon-hourly-learning-schedule.json` | 0–23시 → domain_id·topic_title |
| `config/collector.default.json` | 소스별 `domain_ids` 태그 |
| `config/arkaon-evolution-domains.json` | 도메인 정의 (#054) |

기본 timezone: `Asia/Seoul`

## 시간표 (요약)

| 시간(KST) | domain_id |
|-----------|-----------|
| 0–1 | LIFECYCLE_STEWARDSHIP |
| 2–3 | AUTH_ONBOARDING_UX |
| 4–5 | HOME_SURFACE_OPTIMIZATION |
| 6–7 | TEMPLATE_COMPOSITION |
| 8–9 | TYPOGRAPHY_MOTION |
| 10–11 | SIGNATURE_MOTION |
| 12–13 | VIDEO_TEMPLATE_EFFECTS |
| 14–15 | CROSS_FEATURE_COHERENCE |
| 16–17 | PAYMENT_CHECKOUT_FLOW |
| 18–22 | 복습 (홈·템플릿·타이포·연동·lifecycle) |
| 23 | INTEGRATION_REVIEW (전 도메인 tagged 소스) |

## 실행

collector 데몬이 자동으로 schedule을 전달한다.

```powershell
py -3.11 -m apf.collector_service `
  --config config/collector.default.json `
  --schedule config/arkaon-hourly-learning-schedule.json `
  --foundry-root . `
  --once
```

## 상태 파일

- `state/hourly-learning-current.json` — 지금 주제 + 마지막 cycle
- `state/hourly-learning/YYYY-MM-DD.jsonl` — 일별 cycle 이력

## 경계

- 자동 구현·배포 없음
- 주제 밖 소스는 `skipped_out_of_topic`으로 건너뜀
- domain tag 없는 legacy 소스는 모든 시간에 후보 (점진 제거 권장)
