# ARKAON 인기 제작 형식 관찰·재설계 지침 v0.1

## 목표

아르카온은 사용자가 만든 로고·명함·랜딩·템플릿·플랫폼의 목적과 intent·DNA를 기준으로, CapCut 템플릿 및 YouTube·TikTok·Instagram의 공개적인 인기 제작 방식을 관찰한다. 최신성과 업종 적합성을 검증한 뒤 결과물의 **표현 원리**만 추천한다. 추천은 사용자가 미리보기에서 승인한 다음 새 revision에 반영한다.

## 관찰 절차

1. 먼저 자산 ID로 소유자·테넌트·원본 intent·DNA·최신 revision을 조회한다. 목적, 대상 고객, 공개 채널, 세로/가로 비율, 접근성, 제작비 제약을 확인한다.
2. 사용자가 허용한 플랫폼과 지역·언어·업종별 공개 자료를 공식 API 또는 허용된 공개 화면에서만 수집한다. 수집 시각, 출처 URL, 조회 범위, 접근 권한, 서비스 약관·상업 이용 조건을 기록한다.
3. 조회수 하나를 ‘인기’로 단정하지 않는다. 최근성, 재생/조회, 좋아요·댓글·공유, 반복 사용의 공개 지표를 플랫폼 내부에서만 비교한다. 지역·장르·표본 수가 다르면 순위를 직접 합산하지 않는다. 데이터가 없으면 ‘인기 검증 불가’로 표시한다.
4. 구성 요소를 원본 콘텐츠와 분리해 기록한다. 예: 시작 2초의 메시지, 화면 전환 빈도, 자막 길이, CTA 위치, 색 대비, 모바일 안전영역, 반복 시청 유도 방식. 저작권 보호 대상인 영상·오디오·이미지·편집 파일·로고·고유 문구를 추출해 학습 자산으로 보관하지 않는다.
5. 각 자산에 맞는 서로 다른 시안 2~3개를 독립 제작한다. '인기 관찰 근거', '왜 이 자산에 맞는지', '변경할 요소', '참고자료 권리·상업 사용 상태'를 한 화면에서 보여 주고 모바일·데스크톱 또는 대상 채널 화면으로 미리본다.
6. 사용자가 선택·수정·승인하면 새로운 revision과 근거 digest를 원본 asset ID에 연결한다. 승인 없는 자동 적용·게시·템플릿 복제는 하지 않는다.

## 출처별 실제 가능 범위

| 출처 | 공식 관찰 단서 | 현재 자동 연결 |
| --- | --- | --- |
| YouTube | Data API의 `videos.list(chart=mostPopular, regionCode=...)`; 지역·카테고리·시각을 함께 기록 | 미구현 |
| TikTok | 승인된 Research API 범위에서는 조회·좋아요·댓글·공유 등 일부 지표를 조회할 수 있음. 접근 승인과 지표 정확성을 별도 확인 | 미구현 |
| Instagram | 허용된 공식 API·공개 정보 범위 내에서 관찰. 다른 계정의 비공개 성과 지표를 임의 수집하지 않음 | 미구현 |
| CapCut | 공개 템플릿 목록과 제공된 인기 표시를 관찰하되 템플릿·음원·효과별 상업 이용 조건을 개별 확인 | 미구현 |

## ARKAON 추천 기록 계약

추천마다 `asset_id`, `source_revision_digest`, `platform`, `region`, `observed_at`, `source_refs`, `metric_scope`, `confidence`, `pattern_principles`, `license_status`, `new_preview_digest`, `owner_decision`을 저장한다. 원본 파일·댓글·프로필 식별자·오디오를 무단 복제하여 저장하지 않는다. 추천 결과는 외부 게시나 고객 플랫폼 운영 승인을 대신하지 않는다.

## 출시 순서

첫 단계는 사용자 제공 URL과 공개 화면의 수동 관찰값으로 시안 추천과 승인 흐름을 검증한다. 그다음 공식 API별 접근 승인, 최신 데이터 수집, 이용 제한·비용, 중복/편향 평가, 차단·삭제·갱신을 별도 PR로 구현한다. 현재는 이 문서만 제안 지식으로 기록하며, 인기 순위 자동 수집 또는 CapCut 템플릿 재사용이 구현됐다고 표시하지 않는다.

## 공식 출처

- YouTube Data API: https://developers.google.com/youtube/v3/docs/videos/list
- TikTok Research API: https://developers.tiktok.com/docs/en/research-api-specs-query-videos
- CapCut Materials License: https://www.capcut.com/clause/material-license-agreement
