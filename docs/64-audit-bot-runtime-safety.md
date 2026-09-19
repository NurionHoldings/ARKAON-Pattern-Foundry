# 64. Audit Bot 자동 연결·원장 안전성

## 적용 시기

Audit Bot은 세 구간에 적용한다.

1. **실시간**: Windows 예약 relay의 15초 주기마다 승인·감사 대기열과 내부 통제를 검사한다.
2. **수정사항 적용 시**: 승인 sandbox의 아르카온 시험이 성공하고 SHA-256 시험 증거가
   생성되면 `enqueue_verified_change`가 필수 감사 작업을 원자적으로 생성한다.
3. **내부감사**: 배포 기준 SHA, 보호 파일 해시, 승인 원장, 학습 원장, 실행·감사
   대기열의 권한 상승과 손상을 relay 주기마다 검사한다.

## 상태 경계

변경 감사 `PASS`는 병합 또는 배포 승인이 아니다. 결과는
`ETERNIAN_AUDIT_REQUIRED`에서 멈춘다. `HOLD`와 `BLOCKED`는 해당 작업을 정지한다.
손상 작업은 `quarantine/audit-bot/`으로 격리하며 뒤의 정상 작업은 계속 처리한다.

내부감사는 결과를 `state/audit-bot-internal-latest.json`에 별도로 저장한다.
배포 기준선이 없으면 `HOLD`, 보호 파일·원장·대기열 변조는 `BLOCKED`다.

## 학습 원장

- 파일별 배타 잠금으로 동시 기록을 차단한다.
- 기록 후 `flush`와 `fsync`를 수행한다.
- `feedback_id`와 review receipt digest 재사용을 금지한다.
- receipt registry의 검토자·역할·원본 manifest·finding·종류와 정확히 결속한다.
- 500건마다 불변 segment로 회전하며 최대 20 segment에서 backpressure를 적용한다.
- segment 사이에도 전역 순번과 이전 record digest 해시체인을 유지한다.
- 아르카온과 에테르니언의 서로 다른 receipt가 모두 있어야 개선안을 제안한다.

## 배포 기준선

`create_deployment_baseline`이 만드는 기준선은 후보일 뿐이다. 운영반영 승인 시점의
commit SHA와 보호 파일 해시를 사용자가 승인한 뒤
`state/audit-bot-deployment-baseline.json`으로 저장해야 한다. 기준선 자체도 SHA-256으로
봉인되며 승인 없이 자동 갱신되지 않는다.

## 운영 안전 경계

- 자동 병합·자동 배포 없음
- 감사 정책 자동변경 없음
- Audit Bot 자기승인 없음
- 승인 원장과 실행대기열이 정확히 결속되지 않으면 감사 실행 없음
- Linux 일반·PostgreSQL CI와 Windows 감사통제 CI가 모두 GREEN이어야 함
