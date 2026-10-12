# Visual_DNA creation hook + real video export integration

## Generation-time integration
Import `registerGeneratedLogo` from `prototypes/logo-evolution/generator-visual-dna-adapter.js` immediately after an image generator returns its actual source blob and structured layers.

Required: assetId, immutable revision, original Blob, source canvas, actual SVG/text/mask layer references, existing Intent_DNA fingerprint and its 12 axes. The adapter computes SHA-256 of original bytes and calls `createVisualDna` to validate IDs, geometry, references and stability.

Returns a `LOCAL_DRAFT` sidecar. This does **not** mark an asset approved, persist to the production DB, or bypass ownership/entitlement gates. Raster-only providers use `registerRasterFallback` and explicitly label semantic segmentation unverified.

## Editor video export
`brush-editor.html` uses `video-export.js` and `stage.captureStream(30)` to record five seconds of the same preview timeline. Browser-supported MP4 is selected first; otherwise WebM. If neither is supported, the export control is disabled.

This is a real client-side video recording, not a deterministic offline render, nor a server-side high-quality MP4. Real-time capture can drop frames. No production renderer/queue, upload, billing or deployment has been enabled.

## Required release gates
- Generator API returns native editable layers; fail closed if layer references are absent.
- Validate asset ownership and entitlement server-side before edit/render.
- Persist immutable original and manifest revisions in authorized storage.
- Review and approve Visual_DNA separately from locked Intent_DNA.
- Add deterministic offline renderer and quality verification for production MP4.
- Browser E2E and integration tests across Chrome, Edge, Safari.
- Preserve repository PRODUCT_IMPLEMENT_HOLD until the release process authorizes implementation.
