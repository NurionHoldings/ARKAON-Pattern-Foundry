# ARKAON authorized seller storefront reconstruction — analysis packet

Source: https://github.com/NurionHoldings/Clearance-sale/blob/feat/seller-categories-pg-architecture/docs/authorized-storefront-reconstruction.md

New capability: with a seller's documented authority, reconstruct their existing shop as a **new Clearance-sale-hosted seller shop**. The source store supplies permitted catalog, assets and design references only. Checkout remains the Clearance-sale internal checkout using the seller-selected onboarded PG.

## Intent_DNA
JOURNEY: seller authorization -> source classification -> licensed export/import -> quarantine -> independent theme reconstruction -> seller preview -> tests -> ETERNIAN audit -> publication.
OBJECT: ImportJob, ImportAsset, ImportProduct, Provenance, StorefrontTheme, ConsentEvidence.
INVARIANT: no copying proprietary themes/code without license, no unauthorized scraping, no customer/payment credential ingestion, no production publication without seller/ETERNIAN/operator approvals.
RISK: copyrighted assets, injection, wrong price/stock, tenant cross-access, source API policy change.

## ARKAON development tasks
- Inspect supported official platform export/API interfaces; maintain evidence-based capability registry and unsupported HOLD.
- Draft isolated import pipeline, schema normalization, duplicate/SKU detection, image provenance and rights verification.
- Reconstruct theme using independent code and approved assets, generate seller-editable preview and differences report.
- Run injection/asset checks, responsive/accessibility tests, inventory reconciliation and sandbox checkout tests.
- Propose code PR and evidence; do not self-install, bypass access, import personal data or deploy.

Scope note: hosted-only checkout decision remains authoritative. This is content/design migration, **not** external checkout integration.
