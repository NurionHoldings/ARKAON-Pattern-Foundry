# ARKAON reusable management-application builder

## Capability

Given a repository, a plain-language request and authorized source documentation, ARKAON should be able to independently produce a reviewable management application slice: requirements, a scoped data model, role-safe screens, source adapters, tests, deployment instructions and a plain-language operations manual. It should reuse the workflow and templates in `templates/managed-app/`, validate the intake packet with `src/apf/managed_app_packet.py`, then produce code and evidence in a feature branch.

“Independent development” means ARKAON can carry a bounded feature from discovery through implementation and pull request without needing a human to design every file. Existing Foundry governance still applies: an operator authorizes code generation and external system access; production deployment, money movement, secret creation, irreversible data migration and locked Intent_DNA changes are not autonomous actions.

## Build stages

### 1. Understand the operation

- Inspect the current repository, read its instructions, run its existing tests and record the branch/base commit.
- Turn the request into people, jobs, timing, source records, decisions, reports and success measures.
- Write a short glossary in the operator's language. Ask only for information that changes the data model, calculation or external authorization; keep working on independent parts.
- Research comparable systems only when the request needs it. Keep findings, source links, dates and inferences separate.
- Record assumptions and open decisions instead of quietly inventing contract, tax or provider behavior.

Deliverable: completed intake based on `intake.example.json`.

### 2. Set boundaries before design

- Identify every source owner and the exact permission that allows the data to be read.
- Mark personally identifiable data and retain only fields needed for the business outcome.
- Decide which user may create, read, export, approve and correct each record. Enforce tenant/account scope in database queries and exports, not only in the interface.
- For money, contracts, identity, permissions and external systems, make high-impact corrections visible and auditable. A warning must not silently change records or move money.
- Keep provider secrets outside source control and application data tables. Use deployment secret injection and record only the secret reference name.

### 3. Model the durable facts

- Name the business objects and draw their relationships before building screens.
- Keep original source IDs and a normalized source payload digest. Define a unique idempotency key so replays do not create new financial events.
- Keep a posted transaction immutable. Represent refund, cancellation, reversal or adjustment as a linked new event.
- Use integer minor currency units and explicit timezone/date semantics. Store source tax/fee values separately from derived totals.
- Version the business rule or contract rate used for a statement. Snapshot which source events contributed to each close.
- Design the separate-provider-to-bank reconciliation as a match with status and evidence. One payout may combine many orders; never assume one order equals one deposit.

### 4. Build connectors as replaceable adapters

- Use the provider-neutral contracts in `connectors.template.json`; keep provider vocabulary, field paths, status translations and auth inside the adapter.
- Start with manual or CSV intake when the source contract is unavailable. A generic field normalizer is not proof that a provider API is connected.
- For API/webhook activation, collect official documentation, account-owner authorization, sandbox records, stable source IDs, retry/cursor semantics, rate limits, error rules, version changes and signature verification details.
- Never scrape a signed-in page or ask a seller for their platform password. Do not enable a connector until replay, duplicate, cancellation, partial-refund, timeout and permission tests pass.
- Preserve the original source envelope or an access-controlled evidence reference so each normalized row can be traced back.

### 5. Implement one complete user journey

Build the thinnest complete slice in this order:

1. Identity, role scope and server-side validation.
2. Source ingestion into a stable canonical record.
3. Durable persistence with idempotency and audit history.
4. Exception/reconciliation view showing the expected value, observed value and evidence.
5. A user decision or approval step for high-impact changes.
6. A report/export that observes the same authorization scope as the screen.
7. Backup, health/readiness and a rollback/recovery procedure.

Use the repository's current stack and patterns. Do not replace a working stack just to match this example.

### 6. Add explainable analysis

- Produce facts and rule-based exceptions first: missing source periods, amount mismatches, late events, impossible tax values, duplicate candidates and open approvals.
- Every result must show its rule, time range, source rows/counts and a plain-language next step.
- Separate observed facts from inference. “No rows arrived” is a signal to check collection; it is not proof that sales were missed.
- Scope each report and its exports by the same role/tenant rules as the underlying data.
- Add an LLM explanation layer only when a reviewed model connection exists; the model may summarize evidence, not invent ledger facts or perform financial actions.

### 7. Prove it before handoff

Use `acceptance.template.json` as a baseline, then derive tests from the actual request. At minimum test:

- a normal create/read journey;
- other-tenant data cannot appear in UI, exports, search, metrics or errors;
- duplicate delivery and replay are idempotent;
- cancellation, partial/full refund and late correction retain original evidence;
- invalid imports are rejected atomically;
- calculation examples match an independent hand calculation;
- signature failure, expired credentials, provider timeout and retry;
- CSV formula safety, logs without secrets, backup restore and health check.

Do not claim a gate passed if it was not run. Report the exact command and result.

### 8. Package for a real operator

- Provide a reproducible Docker/local start, persistent database volume, HTTPS guidance, secret variable names, database backup and restore commands.
- Write an operations manual for non-specialists: initial setup, daily work, month close, error recovery, CSV examples, escalation owner and limits.
- Create a pull request with scope, assumptions, tests, screenshots/log evidence when available and pending operator decisions.
- Hand off provider questions using `connectors.template.json` and the partner intake checklist. A provider integration stays “pending” until real sandbox evidence exists.

## ARKAON execution loop

1. Read repo instructions and relevant existing Foundry policies.
2. Inspect source repository, current tests, schema, deployment path and prior decisions.
3. Fill intake, connector profiles, acceptance cases, risks and unresolved questions.
4. Run the managed-app packet validator. Fix missing or contradictory fields.
5. Present the bounded plan and external authorization needs. Do not substitute a generated guess for missing provider facts.
6. After the operator has authorized the feature, build in small code/test/doc slices and keep each claim traceable to evidence.
7. Run focused tests after each slice, then the repository's required suite.
8. Create a reviewable pull request and update this project knowledge with outcomes and reusable corrections.

## Learning loop

After each project, retain generalized rules: defect class, failed assumption, useful test pattern, connector field mapping lesson and operational question that prevented rework. Strip credentials, customer data, private contracts and project-specific identifiers first. Update propose-only knowledge and request ETERNIAN review before any locked Intent_DNA change.

## Reference implementation

The `addon-polo` tenant sales project exercises this method: a role-scoped append-only ledger, CSV import, connector intake, settlement differences, monthly commission snapshots, explainable ARKAON checks, Docker instructions and a non-specialist manual. Its provider APIs are deliberately pending because no source-specific agreement, official schema or sandbox authorization was supplied. Use it to copy the engineering pattern, not its specific tax/commission assumptions.
