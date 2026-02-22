# Output Format: specify

Your output MUST be a markdown file written to `specs/<NNN>/spec.md` where
`<NNN>` is the next sequential feature number (check existing directories).

## Required Sections

```markdown
# Feature: <Title>

## Overview
(1-3 sentence summary of what this feature does and why)

## User Stories
### US-1: <Story Title>
**As a** <role>, **I want** <capability>, **so that** <benefit>.

#### Acceptance Criteria
- [ ] AC-1.1: <testable criterion>
- [ ] AC-1.2: <testable criterion>

(repeat for each user story)

## Functional Requirements
- [ ] FR-1: <requirement>
- [ ] FR-2: <requirement>

## Non-Functional Requirements
- [ ] NFR-1: <requirement with measurable target>

## Out of Scope
- <explicitly excluded item>

## Open Questions
- <any unresolved ambiguity — or "None" if all resolved>
```

## Rules
- Every AC must be testable (has a clear pass/fail condition)
- Every FR must trace to at least one user story
- NFRs must have measurable targets (not "fast" but "< 200ms p95")
- If no open questions remain, write "None" — do not omit the section
