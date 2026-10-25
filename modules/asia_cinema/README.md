# ASIA HOLDINGS cinema — PR-A input validation

Validates pinned SHA-256 for reference PNG, A-symbol mask, and operator-approved Korean slogan before any render (PR-B/C).

## Run

```powershell
python -m modules.asia_cinema.validate_inputs `
  --manifest inbox/eternian-review/asia-cinema-pr-a-20261025-01/input.manifest.json `
  --repo-root . `
  --report inbox/eternian-review/asia-cinema-pr-a-20261025-01/validation-report.json
```

Exit code `1` when validation fails (`render_allowed: false`).

## Schema

`config/input.manifest.schema.json` — `apf.asia-cinema-input-bundle/v1`

## Policy

- Does not modify source assets or inbox evidence (#125/#124).
- Public JSON reports redact local absolute paths (`<asset:filename>` only).
