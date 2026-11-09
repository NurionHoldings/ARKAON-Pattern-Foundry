# ASIA HOLDINGS cinema — PR-A input validation

Validates pinned SHA-256 for reference PNG, A-symbol mask, and operator-approved Korean slogan before any render (PR-B/C).

## Run

```powershell
python -m modules.asia_cinema.validate_inputs `
  --manifest private/asia-cinema/input.manifest.operator-local.json `
  --repo-root . `
  --report inbox/eternian-review/asia-cinema-pr-a-20261025-01/validation-report.json
```

Exit code `1` when validation fails (`render_allowed: false`).

The committed `inbox/.../input.manifest.json` is a public copy whose asset paths are
`<operator-local:filename>` placeholders; it is not runnable. The runnable manifest with real
paths lives under `private/` (git-ignored) on the operator machine only.

## Schema

`config/input.manifest.schema.json` — `apf.asia-cinema-input-bundle/v1`

## PR-B — fixed-camera Blender scene

Requires Blender 5.2. The PR-B manifest adds `asia_a_symbol_trace`, `asia_bg_plate`, `font_en`, `font_ko`
to the PR-A bundle; approved background and fonts stay operator-local (`private/`), so the `.blend`
is rebuilt from the manifest instead of being committed.

```powershell
$blender = "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
$m = "private/asia-cinema/input.manifest.pr-b.operator-local.json"
$blend = "private/asia-cinema/pr-b-build/asia_holdings_cinema_v1.blend"

python -m modules.asia_cinema.validate_inputs --manifest $m --repo-root . --report <run>/input-validation-report.json
& $blender -b --factory-startup -P modules/asia_cinema/blender/build_scene.py -- --manifest $m --repo-root . --out-blend $blend
& $blender -b $blend -P modules/asia_cinema/blender/validate_scene_invariants.py -- --manifest $m --repo-root . --report <run>/scene-invariants-report.json
& $blender -b $blend -P modules/asia_cinema/blender/export_png_sequence.py -- --out-dir private/asia-cinema/pr-b-build/preview_960x540
```

- `build_scene.py` re-checks every pinned SHA-256 inside Blender before building.
- `scene_invariants.py` (pure Python, unit-tested in CI) forbids transform keyframes, drivers and
  constraints on `CAM_RIG`, `CAM_Main`, `GRP_Logo`, `BG_Plate`, and binds `TXT_*` bodies to the
  approved company literal and slogan SHA-256.
- `vectorize_symbol.py` (needs `opencv-python`, operator machine only) regenerates the A-symbol
  comparison sheet from `config/a_symbol_trace.v1.json`.

## Policy

- Does not modify source assets or inbox evidence (#125/#124).
- Public JSON reports redact local absolute paths (`<asset:filename>` only).
- Committed manifests and registrations never contain operator absolute paths.
- `config/*.json` is pinned by SHA-256 and kept LF via `.gitattributes`; editing the A-symbol trace
  requires operator re-approval.
