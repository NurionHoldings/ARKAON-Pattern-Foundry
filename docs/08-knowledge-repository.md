# 08. 지식저장소와 검색구조

- 명세 ID: APF-KNOWLEDGE-001

## 저장계층

1. Evidence Store: 원본·해시·권한, tenant 격리
2. Analysis Store: 관찰·추론·Intent_DNA·중간결과
3. Pattern Registry: 승인된 불변 Package
4. Search Projection: 키워드·벡터·그래프 인덱스
5. Audit Store: append-only 이벤트

## 검색단위

Pattern, Module, IntentDNA, Domain, Role, State, DataEntity, API, Invariant, FailureMode를 별도 문서로 투영한다. 각 문서는 tenant_scope, classification, status, version, risk_class, source_quality, approval_state를 가진다.

## Hybrid 검색

1. Intent_DNA fingerprint로 후보공간 축소
2. 구조화 필터: 유형·위험·라이선스·상태·호환성
3. BM25 키워드
4. embedding 의미검색
5. pattern relation graph 확장
6. 적용성·품질·재사용증거로 rerank

점수 예시: intent 0.35 + applicability 0.20 + semantic 0.15 + keyword 0.10 + quality 0.10 + reuse 0.10. OFFICIAL 외 결과는 기본 검색에서 제외한다.

## ACL

검색 전과 후 모두 tenant/classification 필터를 적용한다. 벡터 인덱스도 tenant 또는 public 영역별로 물리 분리한다. 검색결과에는 접근 불가 자료의 제목·존재 여부도 노출하지 않는다.

## 캐시

쿼리 캐시 키는 principal, tenant, authority_scope, intent_fingerprint, registry_revision을 포함한다. 권한·Package 상태 변경 시 관련 캐시를 폐기한다.

## 설명 가능성

검색 결과는 점수만 제공하지 않고 matching intent axes, satisfied prerequisites, conflicts, source quality, risk, version, 대체 Package를 반환한다.
