# Fundamental learning gates — patch apply

`main` 기준 학습 게이트만 분리한 커밋 **0d3a63f** (design **33e14c9** strict 내용).

## GitHub 브랜치

`feat/fundamental-learning-gates-strict`

## 로컬 적용

```bash
git checkout main
git apply patches/fundamental-learning-gates-strict-0d3a63f.diff
# 또는
git am patches/0001-Add-strict-fundamental-learning-gate-assessor-split-.patch
```

## 검증

```bash
python -m pytest tests/test_fundamental_learning_evidence.py tests/test_fundamental_learning_gates.py -q
python orchestrator/arkaon-fundamental-learning-gates.py --dry-run
```
