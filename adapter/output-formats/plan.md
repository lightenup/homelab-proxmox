# Output Format: plan

Your output MUST be a markdown file written to `specs/<NNN>/plan.md` in the
same feature directory as the spec.

## Required Sections

```markdown
# Implementation Plan: <Feature Title>

## Architecture Overview
(High-level description of the approach — components, data flow, key
design decisions. 3-5 paragraphs.)

## Technology Choices
| Component | Choice | Rationale |
|-----------|--------|-----------|
| ...       | ...    | ...       |

## File Structure
```
path/to/new/file.ext    — purpose
path/to/modified/file   — what changes
```

## Implementation Steps
### Step 1: <Title>
- **Files**: `path/to/file`
- **Description**: What to create/modify and why
- **Dependencies**: Step N (or "None")
- **Parallel-safe**: Yes/No

(repeat for each step, ordered by dependency)

## Risk Assessment
| Risk | Impact | Mitigation |
|------|--------|------------|
| ...  | ...    | ...        |

## Testing Strategy
- **Unit tests**: What and where
- **Integration tests**: What and where
- **Coverage target**: X%
```

## Rules
- Every step must trace to at least one FR or AC from the spec
- Steps must be ordered by dependency — parallel-safe steps should be marked
- File paths must be concrete — no "somewhere in the project"
- Testing strategy must address how each AC will be verified
