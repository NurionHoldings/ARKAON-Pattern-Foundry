/* Reviewed implementation knowledge, shared by the UI and regression tests. */
((root) => {
  const guides = [
    {
      id: 'motion', title: '메뉴·버튼 전환 효과', scope: 'LANDING',
      keywords: ['전환', '메뉴', '버튼', '애니메이션', '모션', 'animation', 'transition'],
      summary: '클릭 피드백과 화면 전환을 연결해 작업 흐름을 또렷하게 만듭니다.',
      steps: ['클릭한 버튼에 짧은 빛의 파동을 표시합니다.', '지원 브라우저에서 화면 전환을 적용하고 기존 링크 이동을 유지합니다.', '동작 줄이기 설정에서는 애니메이션을 생략합니다.'],
      checks: ['클릭·키보드 Enter·뒤로가기 동작', '동작 줄이기 및 미지원 브라우저 동작'],
      source: 'https://developer.mozilla.org/en-US/docs/Web/API/View_Transition_API',
    },
    {
      id: 'responsive', title: '모바일에 맞는 반응형 구성', scope: 'LANDING',
      keywords: ['모바일', '반응형', '카드', '화면', '배치', '레이아웃', '그리드', 'responsive', 'grid'],
      summary: '기기 폭에 따라 카드와 입력 영역의 배치를 조절합니다.',
      steps: ['CSS Grid의 minmax와 유연한 열 배치로 콘텐츠 폭을 조절합니다.', '좁은 화면에서는 입력·버튼을 읽고 누르기 쉬운 순서로 배치합니다.', '긴 제목과 주소가 화면 밖으로 넘치지 않게 처리합니다.'],
      checks: ['320·390·768·1440px 화면에서 가로 넘침 확인', '긴 한국어 제목과 큰 글자 설정 확인'],
      source: 'https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_grid_layout/Realizing_common_layouts_using_grids',
    },
    {
      id: 'form', title: '입력 검증과 요청 저장', scope: 'PLATFORM',
      keywords: ['입력', '검증', '요청', '저장', '오류', '폼', 'form', 'validation'],
      summary: '누락·형식 오류를 알려주고 작성한 내용을 안전하게 저장합니다.',
      steps: ['필수 항목과 길이·형식을 브라우저 기본 검증으로 먼저 확인합니다.', '기존 작성 내용을 보존하면서 오류 위치와 수정 방법을 안내합니다.', '서버로 보내는 값은 서버에서도 권한과 형식을 다시 검사합니다.'],
      checks: ['빈 값·잘못된 형식·최대 길이 확인', '저장 실패 후 입력 보존과 재시도 확인'],
      source: 'https://developer.mozilla.org/en-US/docs/Learn_web_development/Extensions/Forms/Form_validation',
    },
    {
      id: 'preview', title: '안전한 미리보기', scope: 'PLATFORM',
      keywords: ['보안', '격리', '미리보기', '스크립트', '해킹', 'iframe', 'sandbox', 'security'],
      summary: '생성한 화면을 기존 계정과 분리해 미리 보여줍니다.',
      steps: ['기본 iframe sandbox에서 시작해 꼭 필요한 권한만 허용합니다.', '사용자 입력을 HTML 코드로 실행하지 않고 텍스트로 표시합니다.', '외부 링크를 검증하고 미리보기가 상위 화면을 바꾸지 못하게 합니다.'],
      checks: ['HTML 공격 문자열이 글자로 표시되는지 확인', '계정 데이터 접근·상위 화면 이동 차단 확인'],
      source: 'https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/iframe',
    },
  ];
  function search(query) {
    const words = String(query || '').normalize('NFKC').toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
    if (!words.length) return guides;
    return guides.map(guide => {
      const haystack = [guide.title, guide.summary, ...guide.keywords].join(' ').toLocaleLowerCase();
      const score = words.reduce((sum, word) => sum + (haystack.includes(word) ? 1 : 0), 0);
      return {guide, score};
    }).filter(item => item.score > 0).sort((a, b) => b.score - a.score).map(item => item.guide);
  }
  function buildRequest(guide, current, maxLength = 4000) {
    if (!guides.includes(guide)) throw new Error('UNKNOWN_GUIDE');
    const section = `[구현 방향: ${guide.title}]\n${guide.steps.map((step, i) => `${i + 1}. ${step}`).join('\n')}\n확인할 동작: ${guide.checks.join(' / ')}\n근거: ${guide.source}`;
    const existing = String(current || '').trim();
    if (existing.includes(`[구현 방향: ${guide.title}]`)) return existing;
    const next = existing ? `${existing}\n\n${section}` : section;
    if (next.length > maxLength) throw new Error('REQUEST_TOO_LONG');
    return next;
  }
  const api = {guides, search, buildRequest};
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.APFImplementationGuides = api;
})(typeof window !== 'undefined' ? window : this);
