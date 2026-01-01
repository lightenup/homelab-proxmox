# Implementation Plan: Rebuild Acceptance Gate Hardening (020)

**Branch**: `020-rebuild-acceptance-hardening` | **Date**: 2026-01-01 | **Spec**: [specs/020-rebuild-acceptance-hardening/spec.md](specs/020-rebuild-acceptance-hardening/spec.md)
**Input**: Feature specification from `/specs/020-rebuild-acceptance-hardening/spec.md`

## Summary

Harden rebuild into a strict acceptance gate: deterministic teardown with governed TEARDOWN-001/002 evidence, unambiguous verification with verify.json and summary.verification fields, zero Ansible deprecation warnings, and catalog-governed optional validation report (VAL-001 in phase validation) with allow-missing semantics. Approach: enhance teardown loops (stop/wait/destroy with retries), add verification mode handoff between rebuild and suite, refactor assertion_utils to ansible_facts usage, update verify_evidence.py for JSON+summary alignment via Python stdlib, and add fixtures plus catalog entries.

## Technical Context

**Language/Version**: Bash (scripts), Python 3.x (verify_evidence.py), Ansible 2.16+ (roles/playbooks)  
**Primary Dependencies**: Ansible core modules, Proxmox CLI (qm/pct), Python stdlib only for verify mutations  
**Storage**: Filesystem evidence packs (artifacts/*), no databases  
**Testing**: Offline fixtures via scripts/lab/ci-verify.sh; manual `pve-lab rebuild --apply/--verify` runs  
**Target Platform**: Proxmox host (Debian-based) with nested workload suite; offline runner for fixtures  
**Project Type**: Infrastructure scripting and Ansible orchestration  
**Performance Goals**: Deterministic teardown within bounded retries; no flaky rc=25 errors; clean console (no deprecation noise)  
**Constraints**: No new non-stdlib deps; bounded retries (default 3) with short backoff; verification mutation via stdlib only; phase for VAL-001 = validation  
**Scale/Scope**: Single lab host, single evidence pack per rebuild run, fixtures exercised offline

## Constitution Check

* Spec-driven workflow: ✅ using specs/020-rebuild-acceptance-hardening/spec.md and tasks.md.
* Secrets policy: ✅ no secrets involved; evidence/fixtures only.
* Separation of concerns: ✅ Terraform untouched; changes limited to scripts/Ansible/python verifier.
* Provider/network/storage boundaries: ✅ no provider changes; teardown/verification only.

Result: Gates pass. Re-check after Phase 1 design (post design still compliant).

## Project Structure

### Documentation (this feature)

```text
specs/020-rebuild-acceptance-hardening/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
└── tasks.md
```

### Source Code (repository root)

```text
scripts/lab/
├── lib/rebuild.sh           # teardown loops, evidence writes
├── pve-lab                  # CLI verification mode wiring
├── verify_evidence.py       # verify.json + summary mutation
├── checks.d/catalog.json    # TEARDOWN/VAL entries
├── ci-verify.sh             # offline fixtures
├── fixtures/evidence-packs/ # new teardown/verification fixtures

ansible/
└── roles/assertion_utils    # deprecation cleanup; generate_report templates

docs/
└── operations.md            # rebuild behavior updates (if needed)
```

**Structure Decision**: Single repo with scripts/Ansible/docs touched; no new services or modules.

## Complexity Tracking

No constitution violations; tracking not required.

## NFR Audit Log (Phase 2)

- NFR-001: verify_evidence.py remains stdlib-only (argparse, json, sys, os, pathlib, typing, datetime); PASS 2026-01-01.
- NFR-002: No CI/workflow changes introduced for this feature; only existing non-pipeline change observed at .github/agents/copilot-instructions.md; PASS 2026-01-01.
- NFR-003: Evidence pack contract_version remains 1.x-compatible with current verifier enforcement; PASS 2026-01-01.
