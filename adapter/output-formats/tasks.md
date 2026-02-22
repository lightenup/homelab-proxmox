# Output Format: tasks

Your output MUST be a markdown file written to `specs/<NNN>/tasks.md` in the
same feature directory as the spec and plan.

## Required Sections

```markdown
# Task Breakdown: <Feature Title>

## Summary
- **Total tasks**: N
- **Estimated complexity**: Low / Medium / High
- **Parallel tracks**: N independent tracks identified

## Tasks

### Task 1: <Title>
- **Type**: create | modify | test | config
- **File**: `path/to/file.ext`
- **Plan step**: Step N
- **Depends on**: Task N (or "None")
- **Parallel-safe**: Yes / No
- **Description**: What exactly to do (1-3 sentences)
- **Acceptance**: How to verify this task is done
- [ ] Complete

(repeat for each task)

## Dependency Graph
```
Task 1 → Task 2 → Task 5
Task 1 → Task 3 → Task 5
Task 4 (independent)
```

## Implementation Order
1. Task 1 (no dependencies)
2. Tasks 2, 3, 4 (parallel after Task 1)
3. Task 5 (after Tasks 2 and 3)
```

## Rules
- Every task must map to exactly one plan step
- Every plan step must have at least one task
- File paths must be concrete
- Tasks should be small enough to implement in a single pass
- Dependency graph must be a DAG (no cycles)
