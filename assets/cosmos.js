/* Navigation remains useful without JavaScript; filters enhance the complete catalog. */
(() => {
  const groups = ['create', 'create', 'create', 'create', 'together', 'together', 'manage', 'manage', 'manage'];
  const motion = matchMedia('(prefers-reduced-motion: reduce)');
  const videos = [];
  const visible = new Set();
  const update = video => {
    if (motion.matches || document.hidden || !visible.has(video)) { video.pause(); return; }
    if (!video.getAttribute('src')) video.src = video.dataset.src;
    video.muted = true;
    video.play()?.catch(() => {});
  };
  const observer = new IntersectionObserver(entries => entries.forEach(entry => {
    if (entry.isIntersecting) visible.add(entry.target); else visible.delete(entry.target);
    update(entry.target);
  }));
  const cards = [...document.querySelectorAll('#serviceGrid .card')];
  cards.forEach((card, index) => {
    card.dataset.group = groups[index];
    const slug = new URL(card.href).pathname.split('/').pop().replace(/\.html$/, '');
    const preview = document.createElement('span');
    preview.className = 'service-motion';
    preview.setAttribute('aria-hidden', 'true');
    const video = document.createElement('video');
    video.dataset.src = `/assets/service-clips/${slug}.mp4`;
    video.poster = `/assets/service-clips/${slug}.png`;
    video.muted = video.defaultMuted = true;
    video.loop = video.playsInline = true;
    video.preload = 'none';
    video.tabIndex = -1;
    video.disablePictureInPicture = video.disableRemotePlayback = true;
    video.setAttribute('muted', '');
    video.addEventListener('volumechange', () => { video.muted = true; });
    video.addEventListener('error', () => { video.removeAttribute('src'); video.load(); }, {once:true});
    preview.append(video);
    card.prepend(preview);
    videos.push(video);
    observer.observe(video);
  });
  motion.addEventListener('change', () => videos.forEach(update));
  document.addEventListener('visibilitychange', () => videos.forEach(update));
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
