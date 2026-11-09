# PR-A 구현 제출 — `asia-cinema-pr-a-20261025-01`

**공식 트랙:** [PR #126](https://github.com/NurionHoldings/ARKAON-Pattern-Foundry/pull/126) — `feat/asia-cinema-pr-a-input-schema` → `main` (**미병합, 운영자 승인 대기**)  
**run_id:** `asia-cinema-pr-a-20261025-01`  
**제외:** `feat/asia-cinema-pr-a-solo-20261025` — 보존·사용 중단, 병합 후보 아님

## 합격 기준

| 케이스 | 결과 |
|--------|------|
| 정상 입력 | **PASS** (운영자 로컬 manifest + 디스크 자산) |
| 누락 파일 | **BLOCK** (`FILE_MISSING`) |
| 해시 불일치 | **BLOCK** (`HASH_MISMATCH`) |
| 미승인 슬로건 | **BLOCK** (`SLOGAN_NOT_APPROVED`) |
| 문구 변조 | **BLOCK** (`SLOGAN_HASH_MISMATCH` / `SLOGAN_TEXT_MISMATCH`) |
| 회사명 오류 | **BLOCK** (Pydantic `company_name_literal`) |
| Windows 절대경로 공개 보고서 노출 | **BLOCK** (회귀 테스트, POSIX CI 포함) |

## 관문

| 관문 | 결과 |
|------|------|
| 단위 테스트 `tests/test_asia_cinema_validate_inputs.py` | **8 passed** |
| 실제 자산 검증 (operator-local manifest) | **PASS** (`ok: true`, `render_allowed: true`) |
| GitHub CI (`test`: ruff + pytest, PostgreSQL 통합, Windows 감사, scope) | **PASS** |
| Cursor Bugbot | **PASS** — 경로 노출 지적 해결됨 |

## 변경 파일 (제품 코드)

| 경로 | 역할 |
|------|------|
| `modules/asia_cinema/validate_inputs.py` | 검증·JSON 보고서 (경로 `<asset:filename>` 비공개) |
| `modules/asia_cinema/config/input.manifest.schema.json` | JSON Schema |
| `modules/asia_cinema/README.md` | 사용법 |
| `modules/asia_cinema/__init__.py`, `__main__.py` | CLI |
| `tests/test_asia_cinema_validate_inputs.py` | 자동 테스트 |

## 증거 (inbox)

| 파일 | 비고 |
|------|------|
| `input.manifest.json` | 공개 사본 — 자산 경로 `<operator-local:filename>` 처리, 실행 불가 |
| `validation-report.json` | 공개 보고서 — 절대경로 없음 |
| `run.manifest.json` | 실행 메타데이터 |

실행 가능한 원본(실제 경로 포함)은 운영자 PC의 `private/asia-cinema/`(git 제외)에만 보관합니다.

## 정책

- #125·#124·STEP5/6 증거 **미변경**
- 검증 실패 시 `render_allowed: false` — PR-B/C 진행 차단
- 공개 보고서·커밋된 manifest·등록 파일에 **운영자 절대경로 미포함**

## 제외 (준수)

Blender · FFmpeg · PR-B/C · 운영 배포 — **미구현**

병합 방식: **squash merge** (운영자 결정). 병합 여부는 운영자 승인 후 진행.
