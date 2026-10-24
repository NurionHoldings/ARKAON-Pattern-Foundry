# PR #123 감사 보완 — 작업 순서·합격 기준

에테르니언 읽기 전용 감사(2026-10-24) 후속. **기존 자동시험 PASS**(run `40066376449` / `fc82af73…` 증거)는 유지한다.  
**수정 3건의 해결 판정·전체 감사·개선 인정·병합·운영반영은 HOLD.**

`fc82af73d0adcd754dfcc0834e1f3eb30cc5cb6e` worktree는 **원본 실행본**으로 취급하지 않는다.  
`docs/evidence/brand-elements/arkaon-first/run-arkaon-first-20261024-01/` 및 Eternian 검토 ZIP은 **덮어쓰지 않는다.**

## 작업 순서

1. **로컬 diff·패치** — `docs/evidence/brand-elements/audit-remediation-123/123-audit-remediation.patch`
2. **항목별 시험** — 아래 합격 기준 (Node `node --test tests/brand-*.test.cjs`)
3. **#123 후속 PR 초안** — `PR-DRAFT-123-audit-remediation.md` (base: `sandbox/design-element-editing`, **푸시·병합 HOLD** 명시)
4. **새 SHA 승인 후** — 깨끗한 checkout에서 `tools/test-brand-browser.cjs` 전체 브라우저 재검증 (별도 run ID)

## 보완점·합격 기준

| # | 보완점 | 합격 기준 | 시험 |
|---|--------|-----------|------|
| 1 | 선택 표시 불일치 | `conceptId` 비었을 때 후보 **전부 미선택** = PASS; 후보 패널 없음 = **NOT_RUN**(자동 PASS 금지); **A≠B**, undo 후 **A와 동일**, redo 후 **B와 동일**(단계별 aria만 맞고 undo 무동작이면 FAIL); 기본 시안 전환 | `tests/brand-concept-selection-logic.test.cjs`; CI `tools/test-brand-concept-selection.cjs` |
| 2 | 저장 복원 범위 | save/reopen 비교에 사업·브랜드·연락·concept·`sample`·편집 컨트롤 포함 | `tests/brand-save-restore-fields.test.cjs` + harness `controls()` |
| 3 | SHA 확인 | HEAD/dirty + **실행 중인 harness 스크립트가 candidate checkout의 `tools/` 아래** | `tests/brand-checkout-verify.test.cjs`, `tests/brand-harness-path.test.cjs` |

## 브라우저 재검증 (새 SHA 이후)

- baseline `ab3a2a9…`, candidate = **승인된 새 커밋**
- checkout **clean** (`git status --porcelain` empty)
- 24 조건·undo/redo·save/reopen PASS 시에만 해당 SHA에 browser evidence 결속

## 관련 파일

- `services/brand-studio.js` — `syncConceptSelection`
- `tools/brand-browser-git-verify.cjs`, `tools/brand-browser-restore-fields.cjs`
- `tools/test-brand-browser.cjs`, `tools/measure-brand-elements.cjs`
