# Deprecated scripts ledger

This directory contains deprecated legacy scripts.

Policy reminders:

- Do not reference deprecated script paths from repo code, CI, IaC, or operator docs.
- Prefer Taskfile entrypoints (`task ...`) and Python implementations.

## Status

| Script | Status | Replacement | Notes |
|---|---|---|---|
| add-service.sh | removed | task service:add | Removed after replacement + docs updates |
| change-service.sh | removed | task service:change | Removed after replacement + docs updates |
| remove-service.sh | removed | task service:remove | Removed after replacement + docs updates |
| verify-snmpv3.sh | deprecated-only | monitoring init + manual snmpwalk | Kept for now as a standalone preflight utility |
