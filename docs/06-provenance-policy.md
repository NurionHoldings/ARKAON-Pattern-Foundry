# 06. 출처·라이선스·공용화 정책

- 명세 ID: APF-PROVENANCE-001

## 증거 우선

모든 주장과 패턴은 SourceEvidence로 역추적되어야 한다. 증거는 source_type, locator, owner, acquired_at, license_id, authorization_id, content_hash, excerpt_locator, retention, derivation_allowed를 가진다.

## 사용 판정

- ALLOW: 자체 자산 또는 명시적 위임·호환 라이선스
- RESTRICT: 분석만 가능, 공용화 또는 재배포 불가
- HOLD: 조건·권한 불명
- DENY: 무단·금지·철회·라이선스 충돌

불명확하면 HOLD가 기본이다. 웹에 공개되어 있다는 사실만으로 재사용 허가로 보지 않는다.

## Clean-room 추상화

1. 원본 관찰자는 구조 사실과 증거만 기록한다.
2. 추상화자는 브랜드·문구·식별자·구현 고유값을 보지 않는 sanitized brief를 사용한다.
3. 검증자는 결과와 원본 사이의 표현·코드·고객정보 유사성을 검사한다.
4. 승인자가 공용화 가능성을 확정한다.

## 공용화 Gate

모두 참이어야 한다.

- derivation_allowed=true
- source evidence coverage=100%
- customer identifiers=0
- personal data=0
- secrets=0
- verbatim protected expression=0
- license conflicts=0
- prohibited similarity=0
- semantic utility preserved=true
- required approvals complete=true

## 철회

출처 권한 철회 또는 라이선스 변경 시 영향 그래프를 계산한다. 의존 Package를 REVIEW_REQUIRED로 바꾸고 신규 제공을 중단한다. 재검토 결과에 따라 유지, 재추상화, 폐기한다.

## 공개 GitHub 경계

이 저장소에는 공용 명세, 공개 가능한 Package, 합성 테스트만 저장한다. CLIENT_RESTRICTED/INTERNAL 원본과 그 위치를 유추할 수 있는 메타데이터는 저장하지 않는다.
