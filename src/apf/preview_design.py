"""Shared, self-contained CSS for deterministic preview artifacts.

No remote font, image, script, or runtime stylesheet is required.
"""

FOUNDATION_CSS = """
:root {
  color-scheme: light;
  --night: #0b172a;
  --deep: #152b42;
  --ink: #1d3042;
  --muted: #516779;
  --paper: #f4f3ed;
  --surface: #fffdf8;
  --mint: #087f70;
  --mint-bright: #38d5ad;
  --amber: #e2a446;
  --line: #c8d6d2;
  --focus: #c97119;
  --shadow: 0 24px 70px rgba(11, 23, 42, .11);
  font: 16px/1.6 system-ui, -apple-system, "Noto Sans KR", sans-serif;
  background: var(--paper);
  color: var(--ink);
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body { margin: 0; min-width: 280px; }
a { color: inherit; }
:focus-visible { outline: 3px solid var(--focus); outline-offset: 3px; }
.wrap { width: min(100% - 48px, 1180px); margin-inline: auto; }
.eyebrow { display: inline-block; color: var(--mint); font-size: .76rem;
  font-weight: 850; letter-spacing: .14em; text-transform: uppercase; }
h1, h2, h3 { line-height: 1.13; letter-spacing: -.045em; overflow-wrap: anywhere; }
p { overflow-wrap: anywhere; white-space: pre-wrap; }
.preview-note { font-size: .8rem; color: var(--muted); }
@media (max-width: 700px) {
  .wrap { width: min(100% - 32px, 1180px); }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: .01ms !important;
    transition-duration: .01ms !important; scroll-behavior: auto !important; }
}
"""

LANDING_CSS = """
.site-header { background: var(--night); color: white; }
.site-header .wrap { min-height: 78px; display: flex; justify-content: space-between;
  align-items: center; gap: 20px; }
.site-brand { font-size: 1.1rem; font-weight: 850; letter-spacing: -.025em; }
.site-tag { font-size: .76rem; color: #d9eee9; border: 1px solid #537268;
  border-radius: 999px; padding: 6px 12px; }
.landing-main { padding-block: clamp(20px, 5vw, 64px) 80px; }
.landing-hero { position: relative; isolation: isolate; overflow: hidden;
  min-height: 520px; background: var(--deep); color: white;
  border-radius: 28px; display: grid; grid-template-columns: 1.15fr .85fr; box-shadow: var(--shadow); }
.landing-hero::before { content: ""; position: absolute; z-index: -1;
  width: 430px; height: 430px; right: -110px; top: -135px; border-radius: 50%;
  border: 1px solid rgba(96, 221, 192, .45); box-shadow: 0 0 0 55px rgba(96, 221, 192, .06),
  0 0 0 115px rgba(96, 221, 192, .04); }
.hero-copy { padding: clamp(36px, 6vw, 82px); align-self: center; }
.hero-copy .eyebrow { color: #8ceccf; }
.hero-copy h1 { max-width: 700px; font-size: clamp(2.4rem, 5.5vw, 5.2rem);
  margin: 18px 0 22px; line-height: 1.07; }
.hero-copy p { color: #dae8e8; font-size: clamp(1rem, 1.5vw, 1.18rem); max-width: 590px; }
.hero-art { position: relative; min-height: 360px; align-self: stretch;
  background: linear-gradient(138deg, rgba(60, 190, 166, .08), rgba(232, 181, 96, .11)); }
.art-orbit { position: absolute; width: min(65%, 300px); aspect-ratio: 1;
  border: 24px solid #64d7b6; border-right-color: #f2bd65; border-radius: 48%;
  top: 50%; left: 50%; transform: translate(-50%, -50%) rotate(-26deg);
  box-shadow: 0 24px 40px #03101d55; animation: drift 8s ease-in-out infinite alternate; }
.art-spark { position: absolute; width: 72px; height: 72px; right: 13%; top: 22%;
  background: #f2bd65; clip-path: polygon(50% 0, 61% 39%, 100% 50%, 61% 61%, 50% 100%,
  39% 61%, 0 50%, 39% 39%); }
@keyframes drift { to { transform: translate(-50%, -46%) rotate(-15deg); } }
.actions { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 30px; }
.actions a { display: inline-flex; align-items: center; justify-content: center;
  min-height: 48px; border-radius: 11px; text-decoration: none;
  padding: 12px 20px; font-weight: 750; }
.actions a:first-child { background: #7ae3c4; color: #0b2a2d; }
.actions a.secondary { color: white; border: 1px solid #79959b; }
.story-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-top: 24px; }
.story-panel { background: var(--surface); border: 1px solid var(--line);
  border-radius: 20px; padding: clamp(24px, 3vw, 38px); }
.story-panel h2 { font-size: clamp(1.4rem, 2.5vw, 2.1rem); margin: 13px 0; }
.story-panel p { color: var(--muted); }
.story-panel small { color: var(--muted); }
@media (max-width: 760px) {
  .site-header .wrap { align-items: flex-start; flex-direction: column; padding-block: 18px; }
  .landing-hero, .story-grid { grid-template-columns: 1fr; }
  .landing-hero { min-height: 0; }
  .hero-copy { padding: 32px 25px 10px; }
  .hero-copy h1 { font-size: clamp(2.2rem, 10vw, 3.6rem); }
  .hero-art { min-height: 230px; }
  .art-orbit { width: 175px; border-width: 16px; }
}
@media (max-width: 420px) { .actions a { width: 100%; } }
"""

PLATFORM_CSS = """
.preview-header { background: var(--night); color: white; border-bottom: 3px solid var(--mint-bright); }
.preview-header .wrap { min-height: 76px; display: flex; align-items: center;
  justify-content: space-between; gap: 18px; }
.preview-brand { font-weight: 850; font-size: 1.18rem; letter-spacing: -.025em; }
.preview-nav { display: flex; gap: 20px; font-size: .88rem; color: #d6e6e5; }
.preview-main { min-height: 640px; padding-block: 28px 80px; }
.preview-hero { display: grid; grid-template-columns: 1.15fr .85fr; min-height: 480px;
  background: var(--deep); color: white; border-radius: 26px; overflow: hidden;
  box-shadow: var(--shadow); }
.preview-hero-copy { align-self: center; padding: clamp(32px, 6vw, 70px); }
.preview-hero h1 { font-size: clamp(2.4rem, 5vw, 4.9rem); margin: 16px 0 20px; }
.preview-hero p { color: #d7e8e6; max-width: 560px; }
.preview-hero .eyebrow { color: #8ceccf; }
.hero-graphic { min-height: 350px; display: grid; place-items: center;
  background: radial-gradient(circle at 50% 50%, #347974 0 14%, #173d49 15% 26%,
  #19423f 27% 28%, transparent 29%), linear-gradient(135deg, #235d61, #0e2537); }
.hero-graphic span { display: block; width: 150px; height: 150px; transform: rotate(-17deg);
  border-radius: 40px; border: 18px solid #82e7c5; box-shadow: 0 20px 50px #03111d77; }
.action { display: inline-block; background: #7ae3c4; color: #0b2a2d;
  border-radius: 10px; padding: 12px 20px; font-weight: 750; margin-top: 20px; }
.section-label { margin: 45px 0 14px; color: var(--muted); font-size: .85rem; font-weight: 750; }
.features { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 15px; }
.feature { background: var(--surface); border: 1px solid var(--line); border-radius: 17px;
  padding: 23px; min-height: 180px; }
.feature .number { color: var(--mint); font-size: .8rem; font-weight: 850; letter-spacing: .1em; }
.feature h2 { font-size: 1.3rem; margin: 13px 0 10px; }
.feature p { color: var(--muted); font-size: .85rem; margin: 0; }
.crumb { color: var(--muted); font-size: .82rem; margin: 12px 0 24px; }
.detail-stage { display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(0, .9fr);
  gap: clamp(22px, 5vw, 70px); align-items: center; }
.detail-visual { min-height: 430px; border-radius: 24px; overflow: hidden;
  background: linear-gradient(150deg, #a2dfd0, #2b6972 55%, #132e46);
  display: grid; place-items: center; position: relative; box-shadow: var(--shadow); }
.detail-visual::before { content: ""; width: 48%; aspect-ratio: 1; border-radius: 50%;
  border: 28px solid #eef9d6; transform: rotate(-20deg) scaleX(.82);
  box-shadow: 0 16px 30px #09222c66; }
.detail-visual span { position: absolute; bottom: 23px; left: 23px; color: #fff;
  font-size: .76rem; background: #0b172aaa; padding: 6px 10px; border-radius: 6px; }
.detail-copy h1 { font-size: clamp(2.3rem, 4.6vw, 4.4rem); margin: 16px 0 20px; }
.detail-copy p { color: var(--muted); }
.detail-meta { border-top: 1px solid var(--line); border-bottom: 1px solid var(--line);
  padding: 18px 0; margin-top: 22px; color: var(--muted); font-size: .84rem; }
.empty { grid-column: 1 / -1; }
.preview-footer { border-top: 1px solid var(--line); color: var(--muted); font-size: .8rem; }
.preview-footer .wrap { padding-block: 24px; }
@media (max-width: 760px) {
  .preview-header .wrap { min-height: 64px; }
  .preview-nav { gap: 9px; font-size: .72rem; }
  .preview-hero, .detail-stage { grid-template-columns: 1fr; }
  .preview-hero { min-height: 0; }
  .preview-hero-copy { padding: 34px 25px; }
  .hero-graphic { min-height: 240px; }
  .features { grid-template-columns: 1fr; }
  .detail-visual { min-height: 280px; }
}
"""
