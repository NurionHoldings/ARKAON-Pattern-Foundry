# ARKAON 정확도 보증 (Pattern Foundry)

조회일: 2026-09-16
상태: NARANG RIDER `accuracy.py` 아날로그 이식. 모델 운영 승격은 **BLOCKED**.

## 원칙

전국 평균이 좋아도 한 세그먼트(지사)의 오차가 크면 전국 승격을 허용하지 않는다.
금액 계산은 예측 문제가 아니다. 라이더 순수익과 점주 공헌이익은 정수 원화로 정확히
맞아야 하며, 오차가 있으면 AI 결과를 폐기한다.

예측은 점추정과 구간을 함께 제공한다. 구간이 너무 넓거나 coverage가 낮거나 표본이
오래되면 공개 규칙 fallback 또는 사람 검토로 전환한다. 안전 중요 작업은 사람 검토다.

## 게이트

- out-of-sample MAE, 편향, P90, interval coverage, 세그먼트 격차, baseline 개선
- 금융 태스크는 exactness_required
- 지사 누락·실패·MAE 비율 초과 시 전국 판정 실패
- drift가 기준을 넘으면 해당 모델만 격리

## 추적성

| 요구사항 | 구현 | 시험 |
|---|---|---|
| 표본·편향·꼬리·coverage | ArkaonAccuracyEvaluator | test_accuracy_uses_out_of_sample_error_bias_tail_coverage_and_baseline |
| 금융 정확일치 | AccuracyPolicy | test_financial_tasks_require_exact_integer_results |
| 안전 fallback | disposition | test_unreliable_or_wide_prediction_uses_safe_fallback |
| 전국 게이트 | evaluate_national_accuracy | test_national_rollout_requires_every_branch_to_pass |
