# 53. 우편함 · 방문 전달 · 사용자 승인 · 이행 흐름

- 명세 ID: APF-MAILBOX-001
- 상태: IMPLEMENTED

## 전체 흐름

```text
[ARKAON] 외부 분석·격차·inbox 패킷 → state/mailbox/items (우편함)
    ↓
[에테르니언 / 범] 접속(방문) → POST /v1/console/visitor/deliver
    ↓
[사용자] delivery-messages 수신 → approve / reject
    ↓
[승인] fulfillment-queue (에테르니언 또는 범 담당)
    ↓
[에테르니언/범] complete → FULFILLED
```

## 역할 매핑

| 역할 | 콘솔 role | 하는 일 |
|------|-----------|---------|
| 에테르니언 | `reviewer` | 방문 시 사용자에게 전달 메시지 생성 |
| 범 | `operator` | 방문 시 전달 + 사용자 본인 + 이행 큐(범 담당) |
| 사용자(나) | `operator` (recipient) | delivery 승인/거부 |

## API

| Method | Path | 설명 |
|--------|------|------|
| GET | `/v1/console/mailbox` | 우편함 항목 |
| POST | `/v1/console/visitor/deliver` | 방문자 → 사용자 전달 메시지 생성 |
| GET | `/v1/console/delivery-messages` | 사용자 수신함 |
| POST | `/v1/console/delivery-messages/{id}/approve` | 사용자 승인 → fulfillment enqueue |
| POST | `/v1/console/delivery-messages/{id}/reject` | 사용자 거부 |
| GET | `/v1/console/fulfillment-queue` | 에테르니언/범 할 일 |
| POST | `/v1/console/fulfillment-queue/{id}/complete` | 확보·반영 완료 기록 |

## 저장소

```text
inbox/{research,eternian-review,operator-decision}/*.json   # ARKAON 원본 패킷
state/mailbox/items/*.json                                    # 우편함 인덱스
state/mailbox/delivery-messages/*.json                        # 사용자 전달 메시지
state/mailbox/fulfillment-queue/*.json                        # 승인 후 이행 큐
```

오케스트레이터 full run 후 `sync_from_inbox`로 우편함 갱신.

## 경계

- 자동 구현·배포 없음 (`automatic_fulfill_allowed: false`)
- fulfillment complete는 **기록**만; 플랫폼 코드 직접 변경은 별도 change control

## 구현

```text
src/apf/arkaon_mailbox.py
config/arkaon-mailbox-delivery.json
tests/test_arkaon_mailbox.py
```

격차 탐지: [52-capability-gap-engine.md](52-capability-gap-engine.md)
