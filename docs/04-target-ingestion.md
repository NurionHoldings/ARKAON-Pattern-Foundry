# 04. 분석대상 수집·등록 구조

- 명세 ID: APF-INGEST-001

## 허용 대상

OWNED_SYSTEM, CLIENT_DELEGATED, OFFICIAL_DOCUMENTATION, LICENSED_OPEN_SOURCE만 허용한다. 제3자 상용서비스는 공식 공개문서 범위에서 구조 원칙만 분석하며 UI·문구·코드 복제를 금지한다.

## 등록 파이프라인

1. REGISTER: 이름, 유형, tenant, 담당자
2. AUTHORIZE: 소유·위임·라이선스 증거와 만료일
3. CLASSIFY: PUBLIC/INTERNAL/CLIENT_RESTRICTED/PROHIBITED
4. SCOPE: 포함·제외 영역, 파생·공용화 허용 여부
5. SANITIZE: 개인정보·비밀·실행지시 제거 또는 격리
6. SNAPSHOT: 원본 해시와 immutable manifest
7. INDEX_PRIVATE: tenant 전용 인덱스
8. READY: 승인된 분석 요청만 생성

## Artifact 유형

DOCUMENT, SOURCE_FILE, DB_SCHEMA, API_SPEC, EVENT_SPEC, UI_FLOW, TEST, CONFIG, AUDIT_SAMPLE, INTERVIEW_NOTE. 운영 DB 덤프와 자격증명은 금지한다.

## Manifest

각 artifact는 id, target_id, snapshot_id, media_type, logical_path, content_hash, size, source_evidence_id, classification, contains_personal_data, contains_secret, ingestion_status를 가진다.

## 중복과 변경

동일 target에서 content_hash가 같으면 재수집하지 않는다. Snapshot은 추가 후 수정할 수 없다. 변경은 새 Snapshot과 delta manifest로 표현한다. 분석은 반드시 하나의 snapshot_id에 고정한다.

## 격리

악성 가능성, 프롬프트 인젝션, 개인정보, 자격증명, 출처 누락, 라이선스 충돌은 QUARANTINED. 승인 없이 인덱싱·분석·다운로드할 수 없다.

## 수집 완료조건

권한 증거 유효, 범위 확정, 등급 확정, 금지정보 0건, manifest hash 검증, tenant 격리 검증, Snapshot seal 완료.
