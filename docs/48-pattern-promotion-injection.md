# Pattern Promotion — 공개키·서명 주입 절차

조회일: 2026-09-17  
상태: 운영 eternian은 Foundry 밖. Foundry는 검증·상태 기록만 수행.

## 1. 역할 분리

| 위치 | 보유 |
|------|------|
| **에테르니언 (Foundry 밖)** | Ed25519 **개인키**, 승격 판단 |
| **Foundry** | Ed25519 **공개키**, manifest, 검증 러너 |

Foundry runtime(`pattern_catalog.py`, `pattern_promotion_runner.py`)에는 서명 기능이 없다.

## 2. 운영 주입 절차 (EXTERNAL_ETHERNIAN)

### 2.1 catalog revision 확인

```bash
py -3.11 orchestrator/arkaon-pattern-promotion.py --dry-run
```

출력의 `catalog_revision`을 manifest에 바인딩한다.

### 2.2 공개키 주입

에테르니언 측 개인키 파일(32바이트 raw 또는 urlsafe-b64)에서 공개키를 추출:

```bash
py -3.11 tools/pattern_promotion_sign.py export-public-key --private-key PATH/TO/ethernian.key
```

`config/arkaon-pattern-promotion.json`에 반영:

```json
{
  "ethernian_public_key_b64": "<export 출력값>",
  "accept_test_vector_decisions": false
}
```

### 2.3 패턴별 서명 manifest 생성

승격할 `pattern_id`마다 외부 개인키로 서명:

```bash
py -3.11 tools/pattern_promotion_sign.py sign-manifest \
  --private-key PATH/TO/ethernian.key \
  --pattern-ids apf.public.intent-dna-lock apf.public.tenant-bound-ownership apf.public.hash-chained-ledger \
  --catalog-revision <2.1에서 확인한 revision> \
  --source EXTERNAL_ETHERNIAN \
  --output config/pattern-promotion-manifest.json
```

각 decision은 다음에 결합된다:

- `pattern_id`, `package_hash`
- evidence/test digest
- `catalog_revision`, `policy`, `expires_at`, **one-time nonce**
- Ed25519 signature

### 2.4 검증 실행

```bash
py -3.11 orchestrator/arkaon-pattern-promotion.py
```

- `verified_count >= 3` → `reuse_proof` digest 생성
- nonce replay·만료·catalog 불일치 → **fail-closed REJECTED**

## 3. 로컬 TEST_VECTOR 데모 (운영 승인 아님)

```bash
py -3.11 tools/pattern_promotion_sign.py demo-test-vector --apply
py -3.11 orchestrator/arkaon-pattern-promotion.py
```

- ephemeral 키로 3개 후보만 서명
- `accept_test_vector_decisions: true` 필요
- 예시 파일은 `config/examples/*.test-vector.example.json`에도 저장

**운영 전 되돌리기:**

```json
// config/arkaon-pattern-promotion.json
"ethernian_public_key_b64": null,
"accept_test_vector_decisions": false

// config/pattern-promotion-manifest.json
"decisions": []
```

## 4. map ops ADVISORY 데모 (별도)

ETA shadow Δ3000s (> tolerance 900s)로 eternian-review inbox 패킷 생성:

```bash
py -3.11 tools/demo_map_ops_advisory.py
py -3.11 orchestrator/arkaon-orchestrator.py --demo-map-ops-advisory
```

`--dry-run`은 경로만 반환하고 파일을 쓰지 않는다.

## 5. 콘솔 확인

- `/v1/console/pattern-promotion` — verified/pending/reuse_proof
- `/v1/console/inbox?stage=eternian-review` — map-ops·plaza 등 패킷
