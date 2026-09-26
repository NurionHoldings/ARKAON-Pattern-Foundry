# Pattern Promotion and Reuse Proof Runner

조회일: 2026-09-17  
상태: #042 harness operational runner. Production promotions remain external.

## 역할

- 30개 후보 catalog validation (`validate_catalog`)
- `config/pattern-promotion-manifest.json`의 외부 Ed25519 서명 검증
- 3개 이상 verified 시 `build_reuse_proof` digest 생성
- 결과 → `state/pattern-promotion/*.json`, 콘솔 `/v1/console/pattern-promotion`

## 경계

- Foundry runtime은 **공개키만** 보유. 개인키·운영 승격은 외부.
- `production_promotion_allowed`는 항상 false.
- `TEST_VECTOR` 결정은 policy flag가 true일 때만 허용 (테스트 전용).
- reuse proof는 구조적 digest만 생성. 부업장터 실측 baseline 비교는 별도 M6 작업.

## CLI

```bash
py -3.11 orchestrator/arkaon-pattern-promotion.py --dry-run
py -3.11 orchestrator/arkaon-orchestrator.py --dry-run
```

`--dry-run` orchestrator는 inbox 파일을 쓰지 않고 `inbox_packet_plan`으로 예정 경로·종류를 반환한다.

공개키·서명 주입 절차와 TEST_VECTOR 데모는 [48-pattern-promotion-injection.md](48-pattern-promotion-injection.md) 참조.

## 구현

```text
src/apf/pattern_promotion_runner.py
config/arkaon-pattern-promotion.json
config/pattern-promotion-manifest.json
orchestrator/arkaon-pattern-promotion.py
tests/test_pattern_promotion_runner.py
```
