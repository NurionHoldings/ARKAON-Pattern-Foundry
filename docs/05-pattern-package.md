# 05. Pattern Package 표준

- 명세 ID: APF-PACKAGE-001
- 디렉터리: packages/{namespace}/{slug}/{semver}/

## 필수 파일

- manifest.yaml
- intent-dna.yaml
- pattern.md
- applicability.yaml
- interfaces.yaml
- invariants.yaml
- tests.yaml
- provenance.yaml
- security.yaml
- changelog.md

## manifest 핵심 필드

```yaml
schema_version: apf.package/0.1
package_id: uuid
namespace: nurion.common
slug: approval-with-escalation
version: 1.0.0
status: OFFICIAL
pattern_type: WORKFLOW
risk_class: MODERATE
intent_dna_id: uuid
source_evidence_ids: [uuid]
compatibility: {}
relations: []
approved_by: [principal-id]
approved_at: RFC3339
content_hash: sha256
```

## 내용 기준

pattern.md는 문제, 맥락, 해결구조, 참여자, 정상흐름, 실패·취소·복구흐름, 결과를 포함한다. 구현 기술과 브랜드 표현은 핵심 패턴에서 분리한다.

applicability는 requires/all, prefers/any, excludes/any를 기계 판독 가능하게 기록한다. interfaces는 ports, commands, queries, events를 정의한다. invariants는 반드시 참이어야 하는 규칙과 위반코드를 정의한다.

tests.yaml은 positive, negative, authorization, concurrency, recovery, contamination 사례를 Given/When/Then으로 포함한다.

## 버전

- MAJOR: 의미·불변조건·인터페이스 비호환
- MINOR: 호환 기능·적용범위 추가
- PATCH: 의미를 바꾸지 않는 문서·검증 보완

공식 버전은 수정하지 않는다. 취약 패턴은 DEPRECATED 또는 REVOKED로 전환하고 replacements를 지정한다.

## 품질점수

traceability 25, abstraction 20, completeness 20, security 15, testability 10, reuse_evidence 10. 최초 OFFICIAL은 80점 이상이며 필수 검증 ERROR 0건이어야 한다.
