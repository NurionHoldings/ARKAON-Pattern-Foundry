# ARKAON 유사 관리 프로그램 독자 개발 역량

## 목표

아르카온이 자연어 요청을 받아 관리 프로그램을 요구사항, 데이터 구조, 사용자 권한, 화면, 커넥터, 분석 규칙, 테스트, 배포자료와 실무자 설명서까지 일관되게 설계하고 구현 초안으로 제출하도록 합니다. 새 프로젝트마다 사람에게 세부 파일 설계를 받아야 하는 상태에서, 아르카온이 필요한 산출물을 스스로 분해·작성·검증하고 사람은 사업 결정과 고위험 승인을 맡는 상태로 발전시킵니다.

## 재사용 자산

- `knowledge/implementation-playbooks/managed-app-builder.md`: 조사부터 운영 인계까지의 제작 절차와 결정 규칙
- `config/arkaon-managed-app-builder.json`: 기능 플래그와 승인 경계
- `templates/managed-app/intake.example.json`: 이번 tenant sales 프로그램을 채운 요구사항 예제
- `templates/managed-app/connectors.template.json`: 공급사 중립 커넥터 프로필과 공통 이벤트 계약
- `templates/managed-app/acceptance.template.json`: 권한·중복·환불·계산·연동·백업 인수 조건
- `src/apf/managed_app_packet.py`: 요구사항 패킷 검증 및 구현 계획 초안 생성
- `tests/test_managed_app_packet.py`: 완성 예제, API 승인 실패, 배포 승인 게이트와 계획 생성을 검증

## 사용할 때

```bash
python src/apf/managed_app_packet.py templates/managed-app/intake.json --plan-out reports/managed-app-plan.md
```

신규 작업은 예제 JSON을 복사해 요구사항을 채웁니다. API나 웹훅을 켜려면 `owner_authorized`, 공식 문서, 변하지 않는 원본 이벤트 ID와 외부 비밀 저장소 참조를 넣어야 합니다. 빠진 정보는 에러 또는 열린 질문으로 남기고, 임의값으로 채우지 않습니다.

## 개발 권한과 안전 경계

기본 기능은 요구사항 패킷 검사와 계획 초안 생성입니다. 기능 구현은 요청된 저장소 지침과 승인된 작업 범위에서 독립적으로 진행해 브랜치·테스트·문서가 포함된 PR을 제출할 수 있습니다. `config/arkaon-co-creation-codegen.json`의 operator approval digest 요구 및 `automatic_deploy_allowed=false`를 그대로 지킵니다. 이 역량팩은 잠금 규칙을 풀지 않습니다.

외부 업체 API 연결에는 공식 계약·업체/계좌 소유자 동의·샌드박스 자료가 필요합니다. 운영 배포, 실제 비밀키, 원장 이전, 돈 이동, 계약·세무 규칙 결정 및 locked Intent_DNA 변경은 아르카온의 자율 결정에 넣지 않습니다.

## 이번 프로그램을 통한 학습 예시

`addon-polo`는 아르카온이 재사용할 수 있는 첫 운영 사례입니다. 테넌트(입점업체) 범위가 있는 매출 원장, 환불 역분개, 입금 차이 화면, 표준 필드 변환기, 공급사 협의 준비화면, 월별 명세, 규칙 기반 관리분석, Docker 실행과 쉬운 실무자 매뉴얼을 포함합니다. 협의되지 않은 공급사 API는 연결되었다고 주장하지 않고 준비 상태로 남깁니다.

연동 준비와 구현 과정에서 얻은 반복 규칙은 민감정보를 제거한 뒤 propose-only 지식으로 제안합니다. 에테르니언 검토 전에 feature-intent를 잠그지 않습니다.
