# ARKAON Logo Evolution — render pipeline contract (draft)

## Current boundary
The browser prototype can locally preview masks and export a short WebM recording.
No production MP4 worker, server API, billing, authorization, queue, or job persistence is implemented.

## Proposed MP4 export pipeline
1. Client submits approved logo ID/version, effects, level, region masks, timeline, output request.
2. Server authenticates and authorizes logo ownership, entitlement, quotas; never trusts client flags.
3. Validate image/masks (size, alpha dimensions, content type, path handling), limit duration/fps/resolution and effect count.
4. Immutable job ID and idempotency key from source hash, renderer version and canonical config.
5. Queue isolated worker. Generate each frame at exact timestamp `frameIndex / fps` using deterministic masks, timing and source layers.
6. FFmpeg process uses fixed argv, allowlisted codecs and flags (no shell), output `libx264`, `yuv420p`, `+faststart`; optional WebM VP9.
7. Verify metadata (frame count, dimensions, duration, codec), sampled visual masks and temporal continuity.
8. Store private artifact, server-signed expiring download after entitlement recheck; maintain audit records.
9. Cancel/retry safe; refunds or charging tied to successful verified artifact policy, never client-side completion.

## Rendering invariants
- Pixel-level component alpha masks, not rectangular compositing.
- Each component has editable name, effect, start, duration, loop.
- L1 is original. Effects gated by level and capability suitability.
- Preserve original logo bytes and original source hash.
- No shape movement outside explicitly selected components; default no flashing >3Hz.
- Preview and final use identical parameter semantics and timing.

## Next integration acceptance
- Add brush UI that paints alpha inside the selected region, with undo/redo and preview recomposition.
- Region masks must be serialized with a versioned lossless format; bounds validated on server.
- Introduce real rendering worker and tests before enabling MP4 button.
- Performance benchmark at 1080p and representative 10-logo dataset.
- Product state PRODUCT_IMPLEMENT_HOLD remains unchanged pending approvals.
