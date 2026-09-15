# 실전 관측 증거 번들·독립 검증

## 목적

`PilotObservationLedger`의 특정 시점을 외부 감사자에게 전달하되, 서명 비밀키나 원본
증거를 전달하지 않고 공개키만으로 무결성을 검증한다. 검증은 라이브 원장을 생성·복원·변경하지
않으며 불변 `PilotBundleVerificationResult`만 반환한다.

## 번들 v1

- 스키마: `apf.pilot-observation-bundle/v1`
- 증거 등급: 항상 `PILOT_OBSERVATION`
- 형식: 키 정렬, 공백 제거, UTF-8 canonical JSON
- 내용: 서명된 관측 payload, 항목 hash chain, head hash, 항목 수, 번들 hash와 서명
- 제외: 관측 원문, 개인정보, 자격증명, 비밀키

각 관측 항목의 Ed25519 서명은 payload를 증명한다. 별도의 도메인 분리된 번들 서명은 항목
순서·개수·head hash를 포함한 manifest 전체를 고정하여 전송 중 절단과 재배열을 탐지한다.

## 외부 감사 절차

1. 운영 경계 밖에서 신뢰한 `key_id → Ed25519 public key` 집합을 준비한다.
2. `verify_pilot_observation_bundle(bundle, trusted_observer_keys=...)`를 호출한다.
3. 검증기는 canonical JSON과 정확한 v1 필드 집합을 확인한다.
4. 번들 hash·서명, 항목별 서명, 연속 sequence/hash chain, head, 시간 순서와 ID 재사용을 확인한다.
5. 성공 시 검증 결과만 사용한다. 이 결과에는 원장 append/sign/evaluate 기능이 없다.

알 수 없는 필드, 중복 JSON 키, 다른 증거 등급·버전, 안전하지 않은 metadata, 잘못된 키,
payload 변조, 절단, 재배열은 모두 fail-closed 처리한다. 번들을 import하여 라이브 원장을
재구성하거나 재서명하는 API는 제공하지 않는다.
