# 51. 외부 랜딩·카피 학습 전략 (Wave 1)

- 명세 ID: APF-LANDING-LEARN-001
- 조회일: 2026-09-17
- 상태: STRATEGY / PRODUCT_IMPLEMENT_HOLD

## 우선순위 (사용자 확정)

```text
[1단계 · 지금]  외부 분석 + 학습 축적
[2단계 · 이후]  축적된 경험자료 + 사용자 분야 요청 → 정리 / 제안
```

**1단계에서는 랜딩 HTML·카피 문장을 바로 “생성·게시”하지 않는다.**  
관심도·전환에 강한 AI가 되려면, 먼저 **합법적 외부 신호 → 추상 패턴 → reflective 교훈**을 쌓는다.

2단계는 사용자가 분야·플랫폼·전환 목표를 요청했을 때, Foundry가 보유한 **검증된 교훈·성과 digest·Intent_DNA**만으로 정리·제안한다. 자동 배포·자동 승격은 없다.

## Wave 1 플랫폼

| platform_id | 표기 | 1단계 역할 |
|-------------|------|------------|
| `MAEJINNAM` | 매진남 | 외부 벤치·자사 공개 surface 관측, 전환 Intent 시드 |
| `DOSIRAK_STORE` | 도시락.store | 커merce 랜딩 **구조** 벤치 (Hero·Offer·Trust·CTA) |
| `WITHER` | wither | 후속 대상; Intent·금지영역 확정 후 동일 파이프라인 |

`docs/09`의 도식락.store 표기와 도시락.store는 **동일 Wave 1 후보**로 두고, 공식 canonical 이름은 operator 확정 전까지 `DOSIRAK_STORE`로 통일한다.

## 1단계 — 외부 분석·학습 (우선)

### 허용 입력 (`docs/13`, `docs/42` 정렬)

| 소스 | 허용 | 금지 |
|------|------|------|
| 공식 HTTPS 문서·공개 landing URL | 섹션 순서, CTA 개수, 헤딩 깊이, 폼 필드 수 | 문구·디자인·코드 원문 저장 |
| 1st party 캠페인 성과 (승인 후) | CTR·전환·체류 **수치** + **카피 각도** 태그 | PII, 비밀, 원문 A/B raw export |
| 블로그·홍보문·바이럴 카피 | **발견 신호** (주제·톤·길이 bin) | Pattern 단독 근거, 문장 복제 |
| research watch / surface observation | structural digest | competitor verbatim |

### 학습 산출 (저장 형태)

1. **Landing Structure Pattern** — `hero-single-cta`, `proof-before-offer`, `scarcity-with-deadline` 등 **설득 구조**만
2. **Copy Angle Tag** — `numeric-benefit`, `question-hook`, `social-proof-above-fold` (문장 X)
3. **Reflective Lesson** — `#049` append-only: 채택·기각·실패·회귀와 baseline 대비
4. **Performance Digest** — tenant-scoped; `impression`, `ctr`, `conversion` + pattern_id 바인딩

### 분석 파이프라인

```text
DISCOVER (공개 surface / 승인 manifest)
  → QUALIFY (Intent 관련성 ≥ 0.30, docs/13)
  → ROUTE_BY_INTENT (플랫폼 Landing Intent_DNA)
  → COMPARE (Wave 1 간 공통 구조 vs 차이)
  → ABSTRACT (clean-room pattern 후보)
  → VERIFY (contamination·복제·라이선스 gate)
  → LESSON (reflective-lessons append, eternian-review when required)
```

전분야 진화 커리큘럼(서체·템플릿·홈·인증·모션·영상·연동·결제·지속관계)은
[54-evolution-learning-domains.md](54-evolution-learning-domains.md)와
`config/arkaon-evolution-domains.json`을 따른다.

### 기존 모듈 매핑

| 기능 | 모듈 |
|------|------|
| 전분야 진화 도메인 | `evolution_domains.py`, `arkaon-evolution-domains.json` (#054) |
| 공개 surface 구조 관측 | `public_surface_observer.py` (#051) |
| 연구 manifest 변경 감지 | `research_watch.py` (#085) |
| 자산 우선순위 | `asset_investigation.py` (R-011) |
| 경험·UX 감사 (홈 문구·헤딩) | `experience_operations_audit.py` (#048) |
| 교훈 기억 | `reflective_learning.py` (#049) |
| 외부 학습 원칙 | `docs/13-external-learning-strategy.md` |

### 1단계 완료 조건 (Wave 1)

- Wave 1 각 플랫폼 **Landing Intent_DNA** 시드 1건
- 플랫폼별 structural observation digest ≥ 1
- 공통 Landing Structure Pattern 후보 ≥ 5 (cross-platform abstract)
- reflective lesson ≥ 3 (채택·기각·실패 포함)
- verbatim copy / competitor storage contamination **0**

## 2단계 — 분야 요청 시 정리·제안 (추후)

사용자가 분야·플랫폼·전환 목표를 요청하면:

```text
요청 (tenant + domain + conversion_goal)
  → 검색: pattern_packages + reflective-lessons + performance digests
  → 정리: 근거-bound proposal (IMPROVEMENT_PROPOSAL 수준)
  → 제안: Landing section outline + copy **angles** 2~3 (문장 초안은 evidence-linked만)
  → inbox / console (자동 반영 없음)
```

**전제:** 1단계 축적이 없으면 2단계는 `INSUFFICIENT_EXPERIENCE`로 fail-closed.

### 2단계 산출물

- Domain Brief (요청 분야 요약)
- Recommended Structure (섹션 순서·CTA·증거 슬롯)
- Copy Angle Options (각도만; verbatim 경쟁 문구 금지)
- Evidence Table (pattern_id, lesson_id, digest ref)
- Synthesis Test Plan (shadow A/B, 자동 게시 없음)

## 경계 (불변)

- Intent_DNA mutation / owned_asset 자동 승격 / deployment **잠금 유지**
- 홍보문·바이럴 문구 **학습 = 구조·각도·성과 상관**만; 문장 복제 학습 금지
- `automatic_learning`, `production_change` policy flag **false**
- eternian-review 필요 시 inbox 경유; operator-decision 없이 partial-apply 금지

## 다음 구현 후보 (명세만, HOLD 해제 아님)

1. `knowledge/landing-intents/*.json` — Wave 1·2 Intent 시드 (작성됨)
2. `config/arkaon-landing-learning.json` — Wave 1 policy, learning budget, forbidden surfaces
3. `src/apf/landing_learning.py` — DISCOVER→ABSTRACT harness (surface + lesson writer)
4. 콘솔 `/v1/console/landing-learning` — digest·lesson·pattern counts (read-only)

## Wave 2 (참고)

`docs/09` 후속: AI법친, AI배비, AI-ABA — Wave 1 교훈 cross-check 후 동일 1→2단계 적용.
