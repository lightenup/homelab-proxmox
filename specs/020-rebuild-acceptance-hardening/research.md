# Research Notes — Rebuild Acceptance Gate Hardening (020)

## Decisions

### D1: Optional validation report handling
- **Decision**: Use catalog-governed VAL-001 in phase `validation` with `allow_missing_evidence=true` by default; profile may require it.
- **Rationale**: Keeps optional fetch out of teardown noise; governance captures presence/absence without WARN spam.
- **Alternatives considered**: (a) Cleanup phase — conflates with teardown; (b) INFO-only logging without catalog entry — lacks governance; (c) Suite-phase check — ties to workload instead of validation.

### D2: Teardown retry model
- **Decision**: stop → wait-for-not-running → destroy with bounded retries (default 3) for both VM (qm) and LXC (pct); on rc=25 (running), issue stop then retry destroy; fail after retries with evidence.
- **Rationale**: Deterministic convergence, no ignored red output, consistent evidence.
- **Alternatives considered**: (a) Ignore rc=25 — hides teardown failures; (b) single-shot destroy — flaky; (c) infinite retry — risks hang.

### D3: Verification mode contract
- **Decision**: Rebuild sets a verification mode flag consumed by suite to suppress "verification skipped" warnings; suite logs deferral as info; rebuild runs verify_evidence and emits verify.json.
- **Rationale**: Single source of truth for verification intent; removes misleading messaging while retaining audit trail.
- **Alternatives considered**: (a) Duplicate verification in suite and rebuild — redundant; (b) leave skip warning — operator confusion.

### D4: Summary and verify outputs
- **Decision**: verify_evidence.py writes `reports/verify.json` and updates `summary.json` with status/report_path/verifier_version using Python stdlib only.
- **Rationale**: Machine-readable output and governance alignment without new deps.
- **Alternatives considered**: (a) jq mutation — violates stdlib constraint; (b) text-only verify.txt — not machine-friendly.

### D5: Ansible deprecation cleanup
- **Decision**: Refactor roles/assertion_utils to use `ansible_facts[...]` and adjust generate_report templating to eliminate INJECT_FACTS_AS_VARS warnings.
- **Rationale**: Zero deprecation noise requirement; ensures warnings indicate real issues.
- **Alternatives considered**: (a) Suppress warnings — masks regressions; (b) ignore — fails success criteria.

## Open Items

None; clarifications closed in spec.
