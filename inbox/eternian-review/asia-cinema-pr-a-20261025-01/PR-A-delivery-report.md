# PR-A 구현 제출 — `asia-cinema-pr-a-20261025-01`

**브랜치:** `feat/asia-cinema-pr-a-input-schema` (로컬, **main 미병합**)  
**run_id:** `asia-cinema-pr-a-20261025-01`

## 합격 기준

| 케이스 | 결과 |
|--------|------|
| 정상 입력 | **PASS** (로컬 manifest + 디스크 자산) |
| 누락 파일 | **BLOCK** (`FILE_MISSING`) |
| 해시 불일치 | **BLOCK** (`HASH_MISMATCH`) |
| 미승인 슬로건 | **BLOCK** (`SLOGAN_NOT_APPROVED`) |
| 문구 변조 | **BLOCK** (`SLOGAN_HASH_MISMATCH` / `SLOGAN_TEXT_MISMATCH`) |
| 회사명 오류 | **BLOCK** (Pydantic `company_name_literal`) |

**단위 테스트:** `tests/test_asia_cinema_validate_inputs.py` — **7 passed**

## 변경 파일 (제품 코드)

| 경로 | 역할 |
|------|------|
| `modules/asia_cinema/validate_inputs.py` | 검증·JSON 보고서 |
| `modules/asia_cinema/config/input.manifest.schema.json` | JSON Schema |
| `modules/asia_cinema/README.md` | 사용법 |
| `modules/asia_cinema/__init__.py`, `__main__.py` | CLI |
| `tests/test_asia_cinema_validate_inputs.py` | 자동 테스트 |

## 증거 (inbox)

| 파일 |
|------|
| `input.manifest.json` |
| `validation-report.json` |
| `run.manifest.json` |

## 정책

- #125·#124·STEP5/6 증거 **미변경**
- 검증 실패 시 `render_allowed: false` — PR-B/C 진행 차단
- 공개 report에 **로컬 절대경로 미포함** (`<asset:filename>`)

## 제외 (준수)

Blender · FFmpeg · PR-B/C · 운영 배포 — **미구현**

독립 검토 후 병합 여부는 운영자 결정.
