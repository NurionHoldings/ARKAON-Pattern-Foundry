# 56. SNS 정기 분석 (변화·기능·환경 학습)

- 명세 ID: APF-SNS-WATCH-001
- 상태: IMPLEMENTED / RESEARCH_PACKET_ONLY

## 목표

아르카온은 **정해진 시간(KST 0·6·12·18시)** 에 SNS 관련 공개 surface를 분석해
새로운 **기능·포맷·환경 변화** 신호를 학습한다.

## 무엇을 학습하는가

| change_kind | 의미 |
|-------------|------|
| `FEATURE_CHANGE` | shop-link, live-badge 등 기능 태그 변화 |
| `FORMAT_CHANGE` | carousel, short-video-hook 등 포맷 변화 |
| `ENVIRONMENT_CHANGE` | layout/theme/bridge 환경 변화 |
| `SURFACE_CHANGE` | digest 변화 (signal diff 미분류) |
| `BASELINE` | 최초 관측 |

## 허용 입력

| kind | 설명 |
|------|------|
| `LOCAL_MANIFEST` | 운영자가 sanitize한 structural digest (`knowledge/sns-digests/`) |
| `PUBLIC_HTTPS_PROFILE` | **승인된** 공개 link-in-bio·랜딩 HTTPS (robots/terms 준수) |

## 금지

- 게시물 원문·댓글·DM 저장
- 비공개 API·인증 우회
- 경쟁사 카피·디자인 복제
- automatic_learning / production_change

## 설정

```text
config/arkaon-sns-watch.json      — 정책·analysis_hours
config/sns-watch-sources.json     — 채널 등록
state/sns-watch/digests.json      — digest·signal 상태
state/sns-watch/last-run.json     — 마지막 정기 실행
```

## 출력

- `inbox/research/{run_id}-sns-{watch_id}.json`
- schema: `apf.sns-watch-inbox/v1`
- 우편함·승인 흐름 (#053)으로 연결

## 오케스트레이터

매 run 시작 시 `SNSWatchRegistry.analyze()` — **정기 시간대에만** 이벤트 emit.

## 운영자 작업

1. Wave 1 플랫폼별 authorized public URL을 `sns-watch-sources.json`에 등록
2. 또는 SNS export를 structural digest JSON으로 sanitize 후 `knowledge/sns-digests/` 갱신
3. `trend_items`에 click_velocity_bin·category_tag·content_angle_tag 기록 (#058)
4. 변화·surge 감지 시 inbox research packet 검토 → 시장 개척 제안 → reflective lesson

클릭 급등·트렌드·시장 개척 제안: [58-sns-trend-market-proposal.md](58-sns-trend-market-proposal.md)
