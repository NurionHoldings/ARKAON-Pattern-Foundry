# 09. 자체 플랫폼 분석 절차

- 명세 ID: APF-PLAYBOOK-001

## 대상 순서

1. MJN: 주문·거래·지급·권한·보안
2. 노가다뉴스: 콘텐츠·편집·발행·분류·검색
3. 부업장터: 신규 설계에 기존 자산 재사용 검증

후속 대상: AI법친, AI배비, AI-ABA, 도식락.store, wither.

## 한 플랫폼의 완료 정의

### Phase A — 권한과 Snapshot
소유 확인, 범위 확정, 비밀 제거, 코드/문서/DB/API/테스트 manifest 고정.

### Phase B — Intent_DNA
사업목적, 핵심 사용자, 가치교환, 성공결과, 불변조건, 금지영역, 위험, 성공신호를 먼저 확정한다. 분석 예산과 우선순위가 여기서 결정된다.

### Phase C — 구조지도
bounded contexts, actors, role/permission, data owner/SoT, state transitions, commands/queries/events, 정상·실패·취소·복구를 작성한다.

### Phase D — 후보 추출
최소 두 개의 구체 사례에서 동일한 목적·제약·상태구조가 확인되거나, 단일 사례라도 범용성이 논증된 경우 후보화한다. 브랜드·기술 고유값을 구성변수로 바꾼다.

### Phase E — 검증
출처, 라이선스, 오염, 보안, 불변조건, 동시성, 복구, 테스트 가능성, 기존패턴 충돌을 검사한다.

### Phase F — 승인·출시
검토결정, 승인, semantic version, hash, 검색투영을 생성한다.

### Phase G — 재사용 학습
부업장터의 실제 설계에 적용하고 선택시간, 수정횟수, 누락결함, 재작업시간을 baseline과 비교한다.

## 분석 산출물

Target Brief, Intent_DNA, Domain Map, Permission Matrix, Data SoT Map, State Machines, API/Event Map, Failure Catalog, Pattern Candidates, Module Candidates, Validation Report, Reuse Plan.

## 중단조건

권한 불명, Snapshot 변동, 고객정보 오염, 고위험 미해결, Intent_DNA 신뢰도 부족, 분석예산 초과, locked contract 충돌 시 HOLD한다.
