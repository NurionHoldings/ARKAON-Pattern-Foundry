# 자산 intent·DNA 연속성 계약 v0.1

## 목적

로고, 명함, 랜딩, 플랫폼 시안을 결과물로 먼저 보여 주고, 나중에 사용자가 추가 개발을 선택하면 같은 기록을 다시 찾아 이어서 작업한다. 재개 요청은 자산 ID 하나만 믿지 않고 소유자·테넌트·원본 기록·최신 revision을 함께 확인한다.

## 생성 기록

새 자산은 기존 소유자 전용 원장 안에 `intent_dna`를 담는다. 형식은 `apf.asset-intent-dna/1.0`이다.

| 필드 | 의미 |
| --- | --- |
| `asset_id` | tenant·owner·자산 종류·원본 ID로 계산한 안정적인 UUID |
| `source_record_id` | 로고/랜딩 draft ID, 명함 card ID, 플랫폼 dialogue ID |
| `intent_digest` | 개인정보와 원문을 제외한 자산 목적의 해시 |
| `dna`, `dna_digest` | 타입별 시안 특성 및 무결성 지문 |
| `source_revision` | 생성 시점 기준 revision 1 |
| `deployment_state` | 처음에는 `NOT_CONNECTED`; 공개 배포의 증거가 아님 |

생성 이후 수정과 복원은 같은 자산 ID와 생성 DNA를 유지하고, 기존 `revision_digest` 연쇄가 실제 변경 이력을 담당한다. 새 기능은 `source_record_id`로 기존 원장을 owner-bound 조회하고 최신 revision을 확인한 뒤 별도 확장 DNA를 제안한다. 원본 요청과 명함 연락처는 기존 권한이 있는 원장에만 존재한다. 식별자만으로 권한을 부여하거나 타 사용자의 기록을 찾아서는 안 된다.

## 결과물별 다음 개발 연결

- 로고: 벡터 형태·색상·변형 수를 바탕으로 모션·다운로드와 새 시안 revision을 연결한다.
- 명함: 원본 로고 draft ID와 앞·뒷면 타입을 바탕으로 편집을 재개한다. 연락처 내용은 DNA나 공개 링크에 넣지 않는다.
- 랜딩: 정적 HTML/CSS와 모바일·데스크톱 미리보기 정보를 바탕으로 GitHub 저장과 Netlify 공개 개발을 이어간다.
- 플랫폼: 홈·상세 구조와 최초 brief 기록을 바탕으로 계정·API·DB 요구사항 분석을 이어간다. Railway 백엔드 검증 후에만 운영 가능으로 표시한다.

기존 자산은 `intent_dna`가 없을 수 있다. 이 경우 ID를 임의로 재발급하거나 허위 DNA를 채우지 않는다. 기존 원장을 owner-bound로 읽어 명시적인 백필 절차와 검증을 거친 뒤 재사용한다. 현재 구현은 신규 자산의 식별·연속성 기반만 제공하며 실제 GitHub/Railway/Netlify 연결이나 개발 기간 단축 수치가 검증됐다는 뜻은 아니다.
