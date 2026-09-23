# 67. 대화형 정적 웹사이트 초안 v1

## 제공 범위

owner는 한국어 요청으로 `static_landing_page` 초안을 만든다. 서버는 고정된
HTML/CSS 템플릿에 이스케이프한 텍스트만 넣어 미리보기를 만든다. 생성한 문장은
실행 코드, 외부 요청, 결제, 배포 명령으로 해석되지 않는다.

초보 사용자도 계정 준비부터 결과물 검토까지 한 화면에서 이해할 수 있도록 한다.
현재는 **정적 랜딩·홈페이지 초안**만 제작 가능하다. 로고, 명함, SNS 홍보 랜딩,
숏폼, 3D 캐릭터 Addon은 준비 중으로 표시한다.

## 사용자 여정과 정직한 준비 상태

`GitHub 가입 → GitHub Apps 참고 → Meshy 가입·API 문서 안내 → 초안 제작·편집·승인 대기 → Netlify 가입·저장소 연결·배포 안내 참고`

각 단계는 `external_connection_readiness` 계약으로 노출한다. 이 계약은 다음 행동을
보여 주는 `GUIDANCE_ONLY` 상태다. 새 draft에는 이 값을 저장하지 않고 응답에서만
계산해 넣는다. 이전 버전이 저장한 현재형·이전형 readiness 또는 readiness가 없는
schema 1.0 draft는 원래 digest를 검증한 뒤 호환 읽기를 허용하지만, 저장된 readiness는
연결의 증거나 권한 판단으로 사용하지 않는다. 계정, 연결, 저장소, 사이트는 모두
미연결 상태로 시작하며, 사용자가 외부 페이지에서 한 일을 이 서비스가 확인하거나
주장하지 않는다.

- GitHub: [회원가입](https://github.com/signup), [GitHub Apps 공식 참고](https://docs.github.com/en/apps). ARKAON GitHub 연결 기능은 아직 제공하지 않으므로 설치할 ARKAON App은 없다.
- Meshy: [가입](https://www.meshy.ai/), [API 인증 안내](https://docs.meshy.ai/en/api/authentication)
- Netlify: [회원가입](https://app.netlify.com/signup), [Netlify GitHub App 권한·저장소 연결 안내](https://docs.netlify.com/build/git-workflows/repo-permissions-linking/), [저장소에서 배포 안내](https://docs.netlify.com/start/quickstarts/deploy-from-repository/)

이 UI는 외부 로그인, 비밀번호 또는 API 키의 입력·전송·저장, Meshy 작업 생성,
GitHub 저장소 쓰기, Netlify 사이트·배포 생성을 하지 않는다. 특히 Meshy API 키는
Meshy의 안전한 개발자 환경에서만 만들고 관리하도록 안내한다. Netlify에서 Git 연결을
선택하면 해당 저장소 push가 자동 배포를 시작할 수 있으므로, 사용자는 Netlify에서
권한과 production branch를 직접 확인해야 한다. ARKAON은 아직 이 연결이나 배포를
실행하지 않는다.

## 홈·상세 화면 설계 원칙

**시각 탐색은 HOLD다.** 현재 구현은 안내·제작·검토의 정보 구조와 접근성 있는 기본
컴포넌트를 검증하는 화면이다. 새로운 시각 언어를 확정하거나 완성된 디자인 체계라고
주장하지 않는다. 이후 시각 탐색은 별도 가설, 비교 시안, 사용자 검증을 거쳐야 한다.

재사용 가능한 화면 체계는 다음 원칙과 컴포넌트로 구성한다.

| 원칙 | 홈 컴포넌트 | 상세 컴포넌트 | 평가 기준 |
| --- | --- | --- | --- |
| 한 화면에서 다음 행동 제시 | 순서가 있는 시작 단계, 서비스별 공식 링크, 상태 문구 | 선택한 초안의 현재 상태와 다음 단계 | 처음 방문한 사용자가 가입·제작·배포의 순서를 설명할 수 있다. |
| 실제 상태와 안내를 구분 | `안내 전용` 공지, 미연결 상태 | 승인 대기 배지, 자동 구현·배포 불가 문구 | 연결 또는 배포가 완료된 것처럼 보이는 버튼·문구가 없다. |
| 결과물 중심 제작 | 프로젝트 이름·자연어 요청 폼, 제작 가능 범위 | sandbox 미리보기, 버전 선택, 문구 수정 | 사용자가 생성 전과 후의 결과물과 편집 대상을 한눈에 구별한다. |
| 되돌릴 수 있는 검토 | 내 초안 목록 | revision, 변경 메모, 새 revision으로 롤백 | 변경·롤백이 기존 버전을 파괴하지 않는다. |
| 작은 화면과 보조기술 우선 | 한 열로 접히는 카드·충분한 터치 영역 | iframe 제목, 폼 label, 상태 텍스트 | 800px 이하에서 가로 스크롤 없이 핵심 행동을 수행한다. |
| 진행감을 주되 오인시키지 않기 | 번호·경계선·푸른 준비 상태를 가진 세 단계 카드 | 미리보기 프레임, version pill, 승인 상태 badge | 색만으로 상태를 전달하지 않고, 모든 상태가 텍스트로도 읽힌다. |

홈은 “준비 단계 → 제작 범위 → 요청 → 내 초안” 순서로 배치한다. 왼쪽 열은 다음 행동을
알려 주는 온보딩 레일이고, 오른쪽 열은 선택한 결과물을 보는 작업 캔버스다. 준비 단계는
숫자, 서비스 이름, 한 문장 설명, 공식 링크, 텍스트 상태를 같은 순서로 반복한다. 상세는
“결과물 미리보기 → 버전 → 문구 편집 → 승인 대기” 순서로 배치한다. 미리보기는 흰 캔버스와
얇은 경계로 작업 UI와 분리하고, version pill은 과거 결과를 열어 볼 수 있게 한다. 작은
화면에서는 레일과 캔버스가 한 열로 전환된다. 이 시각 규칙은 구현 가능 범위의 안내·제작·
검토 상태만 나타내며, 미구현 연결 상태를 시각적으로 완료처럼 꾸미지 않는다.

## 이용 흐름

`홈 → 한국어 요청 → 미리보기 → 수정 또는 롤백 → OWNER_APPROVAL_PENDING`

수정은 현재 revision digest를 제출해야 한다. 제목과 소개 문구는 별도 입력으로
결정적으로 새 미리보기에 반영한다. 변경 메모는 버전 기록과 ‘이번 반영’ 문구에 남긴다.
롤백도 삭제가 아니라 새 revision을 추가한다. 승인 대기는 외부 동작 권한이 아니다.

## 경계

- 각 draft는 tenant와 owner principal에 결속된다.
- HTML에는 사용자 입력을 마크업으로 해석하지 않는다.
- 원장은 SHA-256 digest로 우발적 변경과 저장 후 불일치를 확인한다. 비밀키나 서명이 없는 digest는 악의적 행위자가 값을 바꾼 뒤 digest를 다시 계산하는 것을 막지 못하므로, 권한 판정이나 독립적인 변조 방어 근거로 쓰지 않는다.
- `automatic_implementation`, `automatic_deployment`, 승인 요청의
  `implementation_allowed`, `deployment_allowed`는 모두 `false`다.
- readiness controls의 외부 로그인, credential 수집·저장, Meshy 작업, 저장소 쓰기,
  배포 생성은 모두 `false`다.
- 기존 `/platform-dialogue`의 역할 분리와 명세 봉인 흐름을 바꾸지 않는다.

## 확장

문서에는 `artifact_type: static_landing_page`를 기록한다. 후속 제작물은 같은
project/draft/revision 경계를 재사용할 수 있지만, 각 결과물은 별도 구현·검증·승인을
거쳐야 한다. 실제 GitHub App OAuth, Meshy credentials, Netlify 연결·배포는 이 안내
계약을 대체하는 별도 tenant-bound authorization, 암호화된 secret 관리, 결과 검증,
사용자별 최종 승인 계약이 마련된 후에만 구현한다.

## 준비 중인 3D 캐릭터 Addon

후속 흐름은 `사용자 이미지 → A-pose 참고 이미지 → 3D 생성 작업 → 리깅 캐릭터
다운로드 → 템플릿·랜딩·플랫폼 배치 미리보기`로 설계한다. 현재 이 흐름은 UI에서
준비 중으로만 표시한다. Meshy 또는 다른 외부 생성 서비스 호출, 파일 업로드, 다운로드,
게시를 실행하지 않는다.

도입 전에 원본 이미지별 사용 동의·권리 근거를 기록하고, A-pose·reference·mesh·rigged
asset 각각의 version과 digest를 tenant-bound job에 연결한다. job 상태, 결과 검증, 배치
미리보기, 명시 승인도 같은 원장에서 분리해 기록한다. 이 계약이 갖춰지기 전에는 어떤
3D 작업도 생성하거나 다운로드할 수 없다.
