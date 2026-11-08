/* Navigation remains useful without JavaScript; filters enhance the complete catalog. */
(() => {
  const groups = ['create', 'create', 'create', 'create', 'together', 'together', 'manage', 'manage', 'manage'];
  const symbols = ['◇', '▷', '▧', '＠', '✧', '↑', '◷', '⌘', '↻'];
  const cards = [...document.querySelectorAll('#serviceGrid .card')];
  cards.forEach((card, index) => {
    card.dataset.group = groups[index];
    const icon = document.createElement('span');
    icon.className = 'card-icon';
    icon.setAttribute('aria-hidden', 'true');
    icon.textContent = symbols[index];
    card.prepend(icon);
  });
  const buttons = [...document.querySelectorAll('[data-filter]')];
  buttons.forEach(button => button.addEventListener('click', () => {
    buttons.forEach(item => item.setAttribute('aria-pressed', String(item === button)));
    let count = 0;
    cards.forEach(card => {
      card.hidden = button.dataset.filter !== 'all' && card.dataset.group !== button.dataset.filter;
      if (!card.hidden) {
        count += 1;
        if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches && card.animate) {
          card.animate([{opacity:0,transform:'translateY(12px)'},{opacity:1,transform:'translateY(0)'}], {duration:260,delay:Math.min(count * 25,150),fill:'backwards'});
        }
      }
    });
    document.getElementById('filterStatus').textContent = `${button.textContent}: ${count}개 서비스`;
  }));
})();
