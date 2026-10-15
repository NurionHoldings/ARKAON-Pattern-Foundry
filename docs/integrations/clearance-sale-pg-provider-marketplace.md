# PG provider onboarding marketplace — ARKAON change packet

Target: https://github.com/NurionHoldings/Clearance-sale/blob/feat/seller-categories-pg-architecture/docs/pg-marketplace-arkaon-integration.md
State: PROPOSED. No autonomous code deployment authorization.

## New business intent
PG companies themselves apply and list payment offerings in Clearance-sale. Seller businesses choose a listed PG, complete PG underwriting and authorize a connection. The platform brokers the integration. ARKAON analyzes officially authorized PG API material, proposes and tests connectors, then provides seller-specific setup assistance or consent-based installation artifacts.

## Intent_DNA affected
WHY, WHO (PG_OPERATOR new principal), VALUE (PG marketplace), JOURNEY (provider onboarding -> seller choice -> underwriting -> connector -> audit -> go-live), OBJECT (PGProvider, PGOffering, SellerPGConnection, ConnectorBuild, ConnectorJob), OWNER (seller choice, PG contract, platform technical delivery), INVARIANT (tenant isolation, no unverified payment, no secret ingestion), CONSTRAINT (SDK licenses, PG contracts, security), RISK (supply-chain compromise, merchant misbinding), EVOLUTION (new PG adapters).

## Requested agent work
- Validate canonical Intent_DNA and mark CORE changes as reopening proposal, never silently lock.
- Draft schema/API/UI for PG provider signup, PG offering review and seller choice; enforce separate provider/seller/operator RBAC.
- Draft a sandbox-only connector factory: parse trusted, licensed API specs in isolation, generate adapter PR and test vectors, never execute untrusted uploaded code or ingest live credentials.
- Provide seller connection wizard, optional signed plugin download and explicit upload consent workflow.
- Build security evidence: webhook authenticity/replay, idempotency, merchant binding, refunds, reconciliation, SDK licensing, secret management, rollback.
- Emit risk-scored proposal and CI evidence to ETERNIAN review queue; require operator approval for merge/release.

This packet is a stored instruction for later ingestion, not proof of running agent execution.
