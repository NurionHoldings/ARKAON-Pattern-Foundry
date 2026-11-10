/* One cached brand asset, muted and decorative; text remains the home link. */
(() => {
  const motion=window.matchMedia('(prefers-reduced-motion: reduce)');
  const videos=[...document.querySelectorAll('[data-header-video]')];
  const visible=new Set();
  const update=video=>{
    if(!motion.matches&&!video.error)video.hidden=false;
    const inEntry=!!document.querySelector('.entry-screen:not([hidden])');
    if(motion.matches||document.hidden||!visible.has(video)||inEntry){video.pause();return;}
    if(!video.getAttribute('src'))video.src='/assets/arkaon-entry-v17.mp4';
    video.muted=true;
    const playing=video.play();if(playing?.catch)playing.catch(()=>{});
  };
  const observer=new IntersectionObserver(entries=>{for(const entry of entries){if(entry.isIntersecting)visible.add(entry.target);else visible.delete(entry.target);update(entry.target);}});
  for(const video of videos){
    video.muted=true;
    video.defaultMuted=true;
    video.volume=0;
    video.setAttribute('muted','');
    video.addEventListener('volumechange',()=>{if(!video.muted)video.muted=true;if(video.volume!==0)video.volume=0;});
    video.controls=false;
    video.removeAttribute('controls');
    video.disablePictureInPicture=true;
    video.disableRemotePlayback=true;
    video.setAttribute('controlslist','nodownload nofullscreen noremoteplayback');
    video.addEventListener('error',()=>{video.hidden=true;});
    observer.observe(video);
  }
  motion.addEventListener('change',()=>videos.forEach(update));
  document.addEventListener('visibilitychange',()=>videos.forEach(update));
  const entry=document.querySelector('.entry-screen');
  if(entry)new MutationObserver(()=>videos.forEach(update)).observe(entry,{attributes:true,attributeFilter:['hidden']});
})();
