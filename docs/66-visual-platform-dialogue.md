# 66. ARKAON Visual Platform Dialogue v1

## 목적

사용자가 전문 개발 용어를 몰라도 플랫폼의 목적, 이용자, 기능, 화면 흐름, 데이터 권한,
비용·결제·정산 구조를 이미지와 대화로 확인하고 최종 명세를 이해한 상태에서 확정한다.

## 상태 흐름

`AWAITING_ARKAON_REVISION → OWNER_REVIEW_REQUIRED → REVISION_REQUESTED →`
`OWNER_REVIEW_REQUIRED → UNDERSTANDING_CONFIRMED → SPEC_SEALED`

수정 요청은 현재 이미지 revision digest에 결속된다. 아르카온은 바로 전 revision을
기준으로 한 새 화면 명세만 제출할 수 있으며, 서버는 구조화된 화면 명세를 SVG 이미지로
재현하고 이미지·명세·revision digest를 각각 기록한다.

## 역할 분리

- 사용자(owner): 플랫폼 목적 입력, 이미지 검토, 수정 요청, 이해 확인, 명세 봉인
- 아르카온(operator): 사용자 요구와 피드백에 따른 구조화 화면 revision 제출
- 에테르니언: 후속 구현 단계에서 명세·Intent_DNA·실제 구현의 독립 일치 감사

owner는 화면 revision을 제출할 수 없고 operator는 사용자 이해 확인이나 명세 봉인을 할
수 없다. tenant와 owner principal이 다른 대화에는 접근하거나 피드백할 수 없다.

## 최종 이해 확인

다섯 항목을 모두 확인해야 한다.

1. 플랫폼 목적
2. 주요 이용자
3. 화면과 이용 흐름
4. 수집 데이터와 권한
5. 비용·결제·정산 구조

하나라도 빠지면 명세를 봉인하지 않는다. 이미지가 보기 좋아도 텍스트 명세와 다르면
수정을 요청해야 한다.

## 안전 경계

- SVG는 서버의 구조화 화면 명세로 재현하며 스크립트를 포함하지 않는다.
- 모든 대화 문서와 이미지는 SHA-256으로 변조를 검사한다.
- stale revision, 이미지 변조, 동시 원장 수정은 차단한다.
- `SPEC_SEALED`는 구현·병합·배포 승인이 아니다.
- 최종 manifest의 `implementation_allowed`와 `deployment_allowed`는 항상 `false`다.
