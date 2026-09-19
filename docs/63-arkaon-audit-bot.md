# 63. ARKAON Audit Bot v1

## 목적

ARKAON Audit Bot은 자기개선 변경의 보고서와 실제 Git diff를 독립적으로 대조하는
읽기 전용 사전 감사기다. 보호 통제의 삭제·변경, 무제한 자원 설정, 특정 PC에 종속된
절대경로, Intent_DNA 및 SHA-256 시험 증거 누락을 탐지한다.

## 판정

- `BLOCKED`: 보호 통제 삭제 또는 무제한 자원 설정 같은 치명적 회귀
- `HOLD`: 보고서 불일치, 보호 통제 변경, 근거 누락 등 독립 검토 필요
- `PASS`: 현재 정책에서 발견 사항 없음

어떤 판정도 병합 또는 배포를 승인하지 않는다. manifest의 `merge_allowed`와
`deployment_allowed`는 항상 `false`다.

## 지속 학습과 자기 업그레이드

감사 후 확인된 적중, 오탐, 누락을 `state/audit-bot-learning.jsonl`에 SHA-256
해시 체인으로 누적할 수 있다. 서로 다른 검토자 2명 이상이 같은 오탐 또는 누락을
확인했을 때만 `SELF_IMPROVEMENT_REQUEST` 후보를 생성한다.
두 검토자는 각각 `ARKAON`, `ETERNIAN` 역할과 SHA-256 review receipt를 제공해야 한다.

학습 결과는 `PROPOSED_ONLY`이며 정책이나 코드를 직접 변경하지 않는다. Audit Bot
자신의 업그레이드도 다음 통제를 그대로 거친다.

`OWNER_APPROVED → SANDBOX_IMPLEMENTING → ARKAON_VERIFYING → ARKAON_VERIFIED →`
`ETERNIAN_AUDITING → ETERNIAN_VERIFIED → DEPLOYMENT_APPROVAL_PENDING`

따라서 단일 아르카온 피드백, Audit Bot 자신의 PASS, 누적 횟수만으로는 정책 승격이나
병합·배포가 불가능하다.

## 실행 예

```powershell
python tools/run_arkaon_audit_bot.py `
  --repository C:\Users\NEW\ARKAON-Pattern-Foundry `
  --base-sha <40자 SHA> `
  --candidate-sha <40자 SHA> `
  --report state\change-report.json `
  --policy config\arkaon-audit-bot.json `
  --approved-scope-digest <승인 scope digest> `
  --approved-path src/apf --approved-path tests `
  --output state\audit-manifest.json
```
