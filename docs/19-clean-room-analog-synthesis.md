# #031 Clean-room Analog Synthesis

## 목적

MJN에서 관측한 후보를 다른 서비스의 구현물로 복제하지 않고, 서로 독립된 공식 자료와 교차 검증해 MJN의 권한·거래·결제 경계에 맞는 새 명세와 실행 가능한 적합성 모델로 재구성한다.

## 역할 흐름

`RESEARCH → ANALYZE → ARCHITECT → BUILD → TEST → AUDIT`

- RESEARCH: 공식 공개 문서만 등록하고 URL, UTC 조회시각, canonical identity digest, 정규화된 관측 내용 digest, 접근 및 이용조건 자세를 남긴다.
- ANALYZE: 외부 프로세스를 단계, 불변조건, 반례로만 추상화한다.
- ARCHITECT: 추상 원칙을 MJN의 서버 권한, 작업 오더, 결제·정산 경계로 치환한다.
- BUILD: 공급사 SDK·문구·API 없이 독립 실행모델을 만든다.
- TEST: 정상, 재시도, 충돌, 철회, 변조 사례를 실행한다.
- AUDIT: 출처 지배, URL·식별자 유출, PII·비밀·고객정보, 승격 시도를 fail-closed로 차단한다.

## 공식 근거

2026-09-15 UTC에 다음 공식 공개 문서를 수동 조회했다. 문서 본문과 인용문은 저장하지 않으며, 참고 전용으로만 사용한다.

- [OpenFGA 모델링 절차](https://openfga.dev/docs/modeling/getting-started): 객체·관계·검사·반복 기반 권한 모델링 원칙
- [Temporal Activity 정의](https://docs.temporal.io/activity-definition): 재시도 가능한 외부 효과와 멱등 실행 경계
- [Stripe Connect 분리 결제와 이체](https://docs.stripe.com/connect/separate-charges-and-transfers): 플랫폼 결제 사실과 후속 자금 이동의 분리
- [Stripe 멱등 요청](https://docs.stripe.com/api/idempotent_requests): 재시도 키, 동일 결과, 변경된 요청 충돌 원칙

각 근거의 URL과 digest는 `knowledge/synthesis/mjn-analog-031.json`에 있다. `content_digest`는 원문 저장 대신 조회 당시 정규화한 관측 사실 묶음의 SHA-256이다. 원문의 라이선스를 코드 재사용 허가로 해석하지 않는다.

## 교차검증 규칙

한 외부 출처만으로 규칙을 채택할 수 없다. 후보별로 (a) 서로 다른 두 외부 계열 또는 (b) MJN 고정 snapshot의 first-party evidence와 하나 이상의 외부 공식 원칙이 필요하다. 전체 캠페인은 최소 세 독립 계열을 요구한다.

## 결과

| 후보 | 독립 재구현 | 핵심 반례 |
|---|---|---|
| `principal-ownership-recheck` | `ScopedAuthorityModel` | 요청자가 소유자 범위를 바꾸거나 철회된 권한을 재사용 |
| `transactional-idempotent-transition` | `OnceTransitionModel` | 같은 키의 다른 의도, 이중 terminal claimant |
| `financial-sot-audit-chain` | `TrustedMoneyModel` | client 금액 신뢰, reversal 무시, 정산 snapshot 변경 |

세 결과는 모두 `ANALOG_SYNTHESIS_CANDIDATE / ETHERNIAN_REVIEW_REQUIRED`이며 `owned_asset=false`다. MJN 저장소 쓰기, Intent_DNA 변경, 자산 승격은 이 단계에서 허용되지 않는다.

## 재현

```bash
pytest -q tests/test_analog_synthesis.py
ruff check src tests
```

validator는 중복 JSON 키, 출처·digest 변조, 단일 출처 지배, 출처 식별자·URL 유출, 민감 필드, 단계 순서 변경을 거부한다.
