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
