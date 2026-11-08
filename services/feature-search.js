(() => {
  const searchForm = document.getElementById('featureSearch');
  const query = document.getElementById('featureQuery');
  const results = document.getElementById('featureResults');
  const status = document.getElementById('featureStatus');
  const {search, buildRequest} = APFImplementationGuides;
  function render() {
    results.replaceChildren();
    const matches = search(query.value);
    status.textContent = matches.length ? `${matches.length}개 구현 방법을 찾았습니다.` : '검토된 가이드에 일치하는 항목이 없습니다. 아래 작업 요청에 필요한 기능을 적어 주세요.';
    for (const guide of matches) {
      const article = document.createElement('article');article.className='feature-result';
      const heading = document.createElement('h3');heading.textContent=guide.title;
      const summary = document.createElement('p');summary.className='muted';summary.textContent=guide.summary;
      const steps = document.createElement('ol');
      for (const step of guide.steps) { const li=document.createElement('li');li.textContent=step;steps.append(li); }
      const actions = document.createElement('div');actions.className='btn-row';
      const apply = document.createElement('button');apply.type='button';apply.textContent='현재 작업에 적용';
      apply.addEventListener('click', () => {
        const message = document.getElementById('message');
        try { message.value = buildRequest(guide,message.value,message.maxLength); }
        catch { status.textContent='작성 내용이 길어 모두 넣을 수 없습니다. 요청을 나누거나 내용을 정리해 주세요. 기존 입력은 유지했습니다.';return; }
        const title = document.getElementById('title');
        if (!title.value.trim()) { title.value=guide.title;document.getElementById('scope').value=guide.scope; }
        document.getElementById('status').textContent='구현 방향을 요청 내용에 반영했습니다. 내용을 다듬고 저장하세요.';
        message.focus();
        message.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'center'});
      });
      const source = document.createElement('a');source.href=guide.source;source.target='_blank';source.rel='noopener noreferrer';source.textContent='공식 구현 문서 ↗';
      actions.append(apply,source);article.append(heading,summary,steps,actions);results.append(article);
    }
  }
  searchForm.addEventListener('submit',event=>{event.preventDefault();render();});
  document.querySelectorAll('[data-feature-query]').forEach(button=>button.addEventListener('click',()=>{query.value=button.dataset.featureQuery;render();}));
  render();
})();
