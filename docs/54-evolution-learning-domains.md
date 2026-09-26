# 54. 전분야 진화 학습 도메인

- 명세 ID: APF-EVOLVE-001
- 조회일: 2026-09-17
- 상태: CURRICULUM LOCKED / EXTERNAL_LEARNING_ONLY

## 목표

아르카온(ARKAON)은 **전 분야 지식을 학습해 진화**한다.  
사용자가 열거한 UX·템플릿·홈·인증·모션·영상·연동·결제·지속관계 영역을 **추상 capability token**으로 고정하고,
1단계에서 외부 관측·교훈을 쌓은 뒤 2단계에서 분야 요청 시 정리·제안한다.

**자동 구현·게시·배포는 하지 않는다** (`PRODUCT_IMPLEMENT_HOLD`).

## 9대 진화 영역 (사용자 확정)

| # | domain_id | 학습 초점 |
|---|-----------|-----------|
| 1 | `TYPOGRAPHY_MOTION` | 서체·색상·텍스트 애니메이션, 접근성·reduce-motion |
| 2 | `TEMPLATE_COMPOSITION` | 템플릿 섹션 리듬, variant, preview sandbox |
| 3 | `HOME_SURFACE_OPTIMIZATION` | 목적 적합 홈 색상·구성, trust-before-offer |
| 4 | `AUTH_ONBOARDING_UX` | 로그인/회원가입 편의, OAuth 경계, 복구 경로 |
| 5 | `SIGNATURE_MOTION` | 차별화 모션 언어, 성능 예산, 고유 피드백 |
| 6 | `VIDEO_TEMPLATE_EFFECTS` | CapCut류 **효과 원리** (타이밍·레이어·비트)—프리셋 복제 금지 |
| 7 | `CROSS_FEATURE_COHERENCE` | 기능 간 내비·딥링크·설정-미리보기 연동 |
| 8 | `PAYMENT_CHECKOUT_FLOW` | 결제 단계·가격 투명·실패 재시도 |
| 9 | `LIFECYCLE_STEWARDSHIP` | 템플릿/플랫폼 **지속 유지**—버전 pin, migration, sunset |
| 10 | `EMERGING_MARKET_SIGNALS` | **신규 시장·세그먼트·수요·규제** 변화 감지 |

추가 영역(`.` 이후)은 동일 스키마로 `config/arkaon-evolution-domains.json`에 append한다.

## 1단계 · 2단계 (docs/51 정렬)

```text
[1단계] DISCOVER → QUALIFY → ABSTRACT → LESSON (토큰·패턴·교훈만)
[2단계] 사용자 분야 요청 → 축적 lesson + Intent_DNA → 정리·제안 (승인 전)
```

## 저장 형태 (원문 금지)

| 산출 | 예 | 금지 |
|------|-----|------|
| capability token | `ux-motion:text-enter-stagger` | 경쟁사 CSS/폰트 파일 |
| abstract pattern | `trust-then-convert` | 랜딩 문구 verbatim |
| observation signal | `signup_field_count` | PII·결제 raw |
| reflective lesson | 채택/기각 + baseline | CapCut preset 파일 |

## 파이프라인 연동

| 기능 | 모듈 |
|------|------|
| 커리큘럼 정의 | `config/arkaon-evolution-domains.json` |
| 로더 | `src/apf/evolution_domains.py` |
| 격차(학습 필요) | `capability_gap.py` — evolution aspiration gaps |
| 공개 surface | `public_surface_observer.py` |
| 연속 수집 | `collector_service.py` (15분) |
| SNS 정기 분석 | `sns_watch.py` (#056, KST 0·6·12·18) |
| 신규 시장 watch | `emerging_market_watch.py` (#057, KST 3·9·15·21) |
| 교훈 | `reflective_learning.py` (#049) |
| 우편함·승인 | `arkaon_mailbox.py` (#053) |

## CapCut·서드파티 편집기 경계

- **허용**: 전환 duration bin, 텍스트 레이어 수, beat marker 존재, export preset **계약** 이름
- **금지**: CapCut 템플릿 파일, 필터 체인, 독점 preset ID 복제

## 지속 관계 ( #9 )

한 번 생성·연결된 템플릿·플랫폼은 **관계가 끊기지 않도록** 다음을 학습한다.

- template version pin + upgrade path
- migration notice + deprecation timeline
- owner continuity contact surface

이는 코드 배포가 아니라 **운영·거버넌스 capability**로 inbox에 요청된다.

## 설정

```text
config/arkaon-evolution-domains.json
```

Wave 1 landing intent 시드는 `evolution_domain_refs`로 관련 domain_id를 참조할 수 있다.
