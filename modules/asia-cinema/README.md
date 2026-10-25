# ASIA cinema PR-A (isolated input validation)

This module is intentionally independent of Blender, FFmpeg, product routes, and production deployment.

Run from the module directory:

```bash
python -m unittest -v test_validate_inputs.py
python validate_inputs.py /path/to/input.manifest.json --report /path/to/report.json
```

Manifest contract (paths are relative to manifest location and must stay inside its directory):

```json
{
  "assets": {
    "reference": {"path": "assets/asia_holdings_reference.png", "sha256": "<64 lowercase hex>"},
    "symbol_mask": {"path": "assets/asia_holdings_A_symbol_mask.png", "sha256": "<64 lowercase hex>"},
    "slogan": {"path": "assets/asia_holdings_slogan_ko.approved.utf8.txt", "sha256": "e9cc11036d72e2b6216b118d1dce41e3abcf345be7d98cdcffd1b05e16bc19a8", "status": "approved"}
  }
}
```

The slogan file must contain exactly `세상을 연결하는 가치, 더 큰 내일을 만듭니다` encoded as UTF-8 without a trailing newline. This validator reports asset names and generic errors, not local absolute paths. It does not write to the source assets. A nonzero exit code blocks subsequent stages.

**Status:** development branch only. The operator's Windows asset files and local evidence manifests are not accessible through this GitHub repository. Their existence, full hashes and licensing must be independently confirmed before PR-A acceptance. No PR, merge, Blender rendering, or deployment is authorized by this change.
