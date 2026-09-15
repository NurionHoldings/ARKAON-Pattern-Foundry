# 11. Intent_DNA 기법

- 명세 ID: APF-INTENT-001
- 목적: 전체 자료를 매번 깊게 분석하지 않고 사업의 변하지 않는 의도를 먼저 찾아 탐색공간과 분석비용을 줄인다.

## 정의

Intent_DNA는 문서요약이 아니다. 시스템이 존재하는 이유와 바뀌면 안 되는 의미를 기계 판독 가능한 축으로 표현한 불변 의도계약이다.

## 12개 축

1. WHY: 해결하려는 근본 문제
2. WHO: 핵심 사용자·수혜자·책임자
3. VALUE: 교환되는 가치
4. OUTCOME: 완료로 인정되는 결과
5. JOURNEY: 최소 가치흐름
6. OBJECT: 핵심 업무객체
7. OWNER: 데이터·결정·금액의 권위 원천
8. INVARIANT: 항상 지켜야 할 규칙
9. CONSTRAINT: 법·보안·사업·기술 제약
10. RISK: 실패 시 피해와 허용한도
11. SIGNAL: 성공·실패를 측정하는 신호
12. EVOLUTION: 확장 방향과 변경금지 핵

## 표현

각 축은 statements[]로 구성하며 statement는 canonical_text, evidence_refs, confidence, stability(CORE/CONFIGURABLE/EXPERIMENTAL), sensitivity, disputed, owner를 가진다. 전체 DNA는 fingerprint와 completeness를 가진다.

## 4단계 추출

### Pass 0 — Seed
프로젝트 정의·잠금계약·대표 흐름만 읽어 12축 초안을 만든다.

### Pass 1 — Evidence routing
각 축의 미확정 사항에 답할 가능성이 높은 artifact만 선택한다. 전체 파일을 무차별 분석하지 않는다.

### Pass 2 — Contradiction
새 증거가 DNA와 충돌하는지만 우선 검사한다. 일치 자료의 재분석은 hash와 semantic cache로 생략한다.

### Pass 3 — Lock
CORE 축을 사람이 승인한다. 이후 분석은 locked DNA와 관계없는 영역을 기본 SKIP한다.

## 분석 예산 절감 규칙

- DNA completeness ≥ 0.85이고 치명 축(WHY, WHO, OUTCOME, OWNER, INVARIANT, CONSTRAINT)이 모두 확정되면 deep analysis 시작.
- 후보 artifact의 intent relevance < 0.30이면 메타데이터만 저장.
- 동일 content_hash는 재분석하지 않는다.
- 동일 intent fingerprint+analyzer version 결과는 재사용한다.
- 영향받은 DNA 축과 연결된 그래프만 증분 분석한다.
- CORE와 무관한 UI 표현·문구·기술 세부는 Pattern 분석에서 제외한다.
- 불확실성이 임계값 이하가 되면 추가 자료수집을 중단한다.
- 정보가치(expected information gain)/비용이 낮은 분석은 SKIP한다.

## 질문 최소화

질문은 다음 조건에서만 생성한다: 치명 축 미확정, 상충 증거, 승인 권한 필요, 잘못 가정하면 고비용. 한 질문은 한 결정을 해결하며 기존 증거로 추론 가능한 질문은 만들지 않는다. 사용자 부재 중에는 안전한 기본값 HOLD를 사용하고 진행 가능한 독립 작업은 계속한다.

## 변경영향

새 변경은 DNA 축과 연결한다. CORE 변경이면 LOCKED_CONTRACT_REOPEN, CONFIGURABLE이면 영향 노드만 재분석, EXPERIMENTAL이면 격리된 비교실험을 수행한다.

## 적합도

신규 사업 Intent_DNA와 Package DNA의 축별 거리로 적합도를 계산한다. CORE 불변조건 충돌은 점수와 무관하게 제외한다. 결과에는 선택 이유, 충족조건, 충돌, 필요한 구성변경을 설명한다.

## KPI

초기 분석 대비 읽은 artifact 60% 감소, 중복 분석 80% 감소, 질문수 50% 감소, 기획시간 50% 감소, 치명 의도누락 0건. 절감률은 AnalysisBudget과 실제 소비량으로 증명한다.
