# Strict learning gate independent review

Reviewed source: 1fecb32c8b78aefa888b2c754d70e6b93807ab7f (split branch).
Render, IAM, services and logo changes are excluded from this review.

Corrections: missing/negative/fractional/boolean/nonfinite failure counts must not
pass metrics validation. Require a full commit SHA and nonblank CI run reference.
Reject traversal and symlink escape in lesson lookup.

Remaining HOLD: validators currently check supplied records, not externally
authenticated CI results or reviewer signatures. Work outcome hashes can only
prove internal consistency of supplied text. Held-out training separation still
depends on declarations/fingerprints rather than corpus membership validation.
Feedback path strings are not verified independent review artifacts.
READY_FOR_REVIEW means a candidate for a reviewer to investigate, not verified
learning improvement or operational readiness. No final improvement recognition,
automatic implementation, merge, deployment or global HOLD release is authorized.

The patch bundle in patches/ describes the original 0d3a63f snapshot only; it
does not contain these independent audit corrections. Review current branch
files for the final implementation. Do not apply that patch directly to main.

## 2026-11-05 학습자료 후속 점검

확인한 main은 `a26baa71e93f1971151c4bb93e537444e95850a1`이며 inbox 세 경로와
reflective-lessons에는 `.gitkeep`만 있다. 이것은 GitHub에 게시된 기록의 상태이며
Windows PC의 학습 실행 중단을 뜻하지 않는다. #115/#116/#117/#122는 미병합이다.
학습 기록 수집, 교훈 재사용, 분리 평가, 개선 인정은 구현·운영 증거를 구분한다.

### 보고서 digest 보완

기존 #117은 평가시각과 단계별 상태만 해시했다. 동일 시각에 실행기록이 1건에서
2건으로 바뀌어도 상태가 같으면 digest와 저장 파일명이 같아 이전 보고서를 덮을 수 있었다.
이제 출력 문서 전체에서 `report_digest`만 제외하고 SHA-256을 계산한다.
`report_digest_algorithm: apf.learning-report-canonical-json/v1`을 함께 기록한다.
규칙: JSON sort_keys=true, ensure_ascii=false, separators=(',', ':'),
allow_nan=false, UTF-8, 추가 줄바꿈 없음. 근거·차단 사유·상위 판정과 알고리즘 식별자도 포함한다.
과거 보고서는 수정하거나 새 규칙으로 재해석하지 않는다. 알고리즘 필드가 없는 과거
보고서는 이전의 상태 요약 해시이며 근거 전체의 무결성을 보증하지 않는다.
이 해시는 보고서에 출력된 내용의 결속이며, 원천 파일 전체의 해시나 외부 진위 검증·서명이 아니다.

회귀시험은 동일 입력의 결정성, 상태가 같아도 근거 변경 시 해시 변경,
같은 시각의 두 보고서 보존, 출력 바이트 규칙 재계산, 차단 사유 변조 감지를 확인한다.
원래 코드에서는 새 회귀시험의 digest 변경 조건이 실패함을 재현했다.
이 보완은 에테르니언 직접 수정이며 아르카온의 별도 1차 검증 완료가 아니다.
명함·로고 UX, #123/#124/#125 증거, Windows 예약 작업, 병합·운영 설정은 변경하지 않는다.
롤백은 이 후속 변경을 revert하되 이미 생성된 보고서는 보존한다.

## 실패 환류 패킷 격리 후속

#127 CI run 41948957844의 test/PostgreSQL/Windows가 모두 성공한 뒤 별도 후속으로 점검했다.
실패 환류 평가는 잘못된 UTF-8·JSON 비객체 입력에서 전체 실행이 중단됐고,
구문이 손상된 JSON·읽기 실패는 누락 사실을 보고하지 않았다.
이제 각 파일에서 인코딩·JSON 구문·읽기 오류·최상위 비객체를 구분해 집계하고
뒤의 정상 패킷 평가를 계속한다. 원본 파일은 이동·수정·삭제하지 않는다.
오류가 하나라도 있으면 이 단계는 PARTIAL로 유지한다. 정상 체인 수는 보존하되
READY_FOR_REVIEW로 올리지 않는다. 오류 메시지 원문이나 절대 경로는 보고서에 싣지 않는다.

시험은 잘못된 인코딩·JSON·배열·null·문자열·숫자·boolean 7종 뒤 정상 체인 처리,
원본 바이트 보존·dry-run 무쓰기·5단계 보고서 유지, 읽기 실패 뒤 후보 처리,
정상 후보 상태 유지까지 포함한다. 집중시험 31 PASS, 변경 Python Ruff PASS.
이 시험은 실제 Windows 수집기 실행 또는 학습 성능 개선의 입증이 아니다.
이 변경은 실패 환류 단계만 대상으로 한다. 다른 단계의 손상 입력·자원 사용 제한은
별도 보완 범위이며 모든 비정상 입력을 격리한다고 주장하지 않는다.
