# Contract: Task Interface

**Feature**: [specs/028-sunset-shell-tools/spec.md](../spec.md)

## Scope

Defines the stable operator-facing interface for day-to-day workflows via `go-task` (`Taskfile.yml`).

This contract is intended to prevent churn in task names, required inputs, and observable outputs.

## Stability Guarantees

- Task names listed in “Top 10 day-to-day workflows (acceptance-test scope)” are stable.
- Tasks must:
  - exit `0` on success
  - exit non-zero on failure
  - print an actionable error on failure
- Tasks must not print or leak secrets.

## Task Naming

- Namespace tasks by domain, e.g.:
  - `service:add`, `service:change`, `service:remove`
  - `inventory:update`
  - `healthcheck:run`
  - `terraform:validate`, `terraform:plan`, `terraform:apply`
  - `deploy:lab`
  - `summary:render`

## Inputs

- Inputs must be passed explicitly via:
  - CLI args (task variables), or
  - environment variables

Inputs should avoid relying on interactive prompts except where explicitly required (e.g., confirmations).

## Outputs

- Human-readable output suitable for operators.
- When artifacts are produced (e.g., inventory file, summary markdown), the task should print the path to the artifact.

## Error Handling

- Missing inputs: fail fast with usage guidance.
- Unsafe operations (apply/remove): require explicit confirmation mechanism.

## Downstream Compatibility

- Introducing `Taskfile.yml` must not break existing CI/IaC/core harness workflows.
- Where a stable script path is referenced and changing the caller is impractical/cumbersome, a shim may remain temporarily.
