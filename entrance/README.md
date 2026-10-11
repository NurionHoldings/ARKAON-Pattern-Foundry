# ARKAON awakening entrance — integration checklist

## Current delivery
- `entrance/index.html`: standalone responsive, keyboard-accessible proof of concept; click/touch awakens the humanoid, opens eyes and smile, iris-style zoom, then redirects to https://arkaonfoundry.netlify.app/.
- Browser speech recognition is optional, user-initiated and feature-detected. A denied microphone does not block access.
- Skip link and reduced-motion behavior are included.
- No changes to existing production site or routes. The visual currently uses CSS geometry; the approved cinematic storyboard is a **reference**, not an integrated motion asset.

## Visual production tasks
1. Produce a consistent single-character face asset set: eyes closed / awake with slight smile / extreme iris macro. Keep composition, proportions and lighting consistent.
2. Export optimized WebP/AVIF poster frames and MP4/WebM motion (muted/autoplay-compatible, mobile bandwidth budget), with fallback stills. Obtain explicit image rights and verify any generated assets before publishing.
3. Replace CSS face with video/frames, implement actual iris camera zoom and crossfade into existing live home without altering its functionality.
4. Avoid page redirect loops: the entry must live at a separate URL, or the existing home must be moved behind an explicit route and the entry shown only once per session. Current standalone page simply links to current home.
5. Browser tests: Android/iOS Safari, keyboard, no mic, reduced motion, slow network, skip, repeated clicks, CSP, cache, mobile viewport.
6. ETERNIAN visual and accessibility audit and operator approval before modifying Netlify production.

## Deployment caveat
The current Netlify project arkaonfoundry is live. Its Git publishing source and deployed app entrypoint have not been proven from the repository; do not switch build output or replace the home based only on this file.
