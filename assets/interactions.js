(() => {
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  document.addEventListener('click', event => {
    const control = event.target.closest('button,a.card,a.btn,.primary-action,.secondary-action,.svc-home,.main-nav a');
    if (!control || reduced.matches || control.disabled || control.getAttribute('aria-disabled') === 'true') return;
    const wave = document.createElement('span');
    wave.className = 'click-wave';
    wave.setAttribute('aria-hidden', 'true');
    control.querySelectorAll('.click-wave').forEach(item => item.remove());
    control.append(wave);
    wave.addEventListener('animationend', () => wave.remove(), {once:true});
    setTimeout(() => wave.remove(), 600);
  });
})();

/* Keep the visible name alive without changing text, labels or form values. */
(() => {
  const excluded = 'script,style,noscript,textarea,input,select,option,code,pre,svg,math,.arkaon-living,[data-arkaon-static]';
  const enhance = root => {
    if (!root || !root.isConnected) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = [];
    if (root.nodeType === Node.TEXT_NODE) nodes.push(root);
    else while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const node of nodes) {
      const parent = node.parentElement;
      if (!parent || parent.isContentEditable || parent.closest(excluded) || !node.data.includes('아르카온')) continue;
      const pieces = node.data.split('아르카온');
      const fragment = document.createDocumentFragment();
      pieces.forEach((piece, index) => {
        if (index) {
          const name = document.createElement('span');
          name.className = 'arkaon-living';
          name.textContent = '아르카온';
          fragment.append(name);
        }
        if (piece) fragment.append(document.createTextNode(piece));
      });
      node.replaceWith(fragment);
    }
  };
  let scheduled = false;
  const pending = new Set();
  const observer = new MutationObserver(records => {
    for (const record of records) {
      if (record.type === 'characterData') pending.add(record.target);
      else record.addedNodes.forEach(node => pending.add(node));
    }
    if (scheduled || !pending.size) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      observer.disconnect();
      for (const root of pending) enhance(root);
      pending.clear();
      observer.observe(document.body, {subtree:true,childList:true,characterData:true});
    });
  });
  enhance(document.body);
  observer.observe(document.body, {subtree:true,childList:true,characterData:true});
})();

/* Direct entries and new tabs have useful ordinary-link fallbacks. */
document.addEventListener('click', event => {
  const back = event.target.closest('a[data-service-back]');
  if (!back || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  let internalPrevious = false;
  try { internalPrevious = new URL(document.referrer).origin === window.location.origin; } catch { /* no referring page */ }
  if (internalPrevious && window.history.length > 1) {
    event.preventDefault();
    window.history.back();
  }
});
