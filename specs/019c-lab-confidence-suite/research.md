# Research: Lab Harness Confidence Suite

**Feature**: `019c-lab-confidence-suite`
**Date**: 2025-12-30

## Decisions

### Confidence Suite Strategy
- **Decision**: Run all validation profiles (`bootstrap`, `hypervisor-control-plane`, `hypervisor-nested-workload`) sequentially plus the Safety Suite.
- **Rationale**: Ensures maximum coverage and confidence in the harness. `bootstrap` validates basic connectivity, `hypervisor-control-plane` validates the PVE installation, and `hypervisor-nested-workload` validates the full stack including nested virtualization.
- **Alternatives Considered**: Running only the max profile (might mask basic issues), or running a subset.

### Evidence Pack Structure
- **Decision**: Use a structured layout with subdirectories (`logs/`, `config/`, `validation/`).
- **Rationale**: Keeps the root directory clean and allows for better organization of artifacts as the number of checks grows.
- **Alternatives Considered**: Flat structure (messy), Ansible-native structure (too complex).

## Unknowns Resolved

- **Execution Order**: Sequential execution confirmed.
- **Artifact Layout**: Structured layout confirmed.
