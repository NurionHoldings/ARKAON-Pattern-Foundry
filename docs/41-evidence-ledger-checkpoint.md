# Evidence Ledger Checkpoint — incubating pattern

출처: NURION_PG 기능 #064, commit 5ead6e00bfc78bb8f7f037866aed645698988f58.

검증된 비어 있지 않은 append-only 증거대장의 레코드 수, 끝점 digest, 대장 report
digest를 하나의 불변 체크포인트로 묶는다. 기록 시각보다 앞선 체크포인트, 손상된
digest, 유효하지 않은 체인은 실패폐쇄한다.

이 구현은 PG의 결제·회원·자격증명·운영자료를 포함하지 않는 일반화된 독립 구현이다.
상태는 ETHERNIAN_REVIEW_REQUIRED이며 공식 30개 public candidate catalog에 자동 추가하거나
owned asset으로 승격하지 않는다. mutation, deployment, automatic merge 권한도 없다.
