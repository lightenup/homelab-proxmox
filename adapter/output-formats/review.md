# Output Format: review

Your output MUST be a markdown file written to `specs/<NNN>/review.md` in
the same feature directory.

## Required Sections

```markdown
# Review: <Feature Title>

## Test Results
- **Tests run**: N
- **Tests passed**: N
- **Coverage**: X%
- **Test command**: `<exact command used>`

## Acceptance Criteria Verification
| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC-1.1 | ... | PASS / FAIL | test name or file:line |

## Functional Requirements Check
| FR | Description | Status |
|----|-------------|--------|
| FR-1 | ... | PASS / FAIL |

## Constitution Compliance
- [ ] Principle I: ...
- [ ] Principle II: ...

## Blocking Issues
(List issues that must be fixed. If none, write "None".)

1. **[severity]** Description — linked to AC/FR/principle

## Observations
(Non-blocking suggestions for improvement.)

## Feedback for Developer
(Specific, actionable instructions if CHANGES_REQUESTED.)

## Verdict
**APPROVED** / **CHANGES_REQUESTED**
```

## Rules
- Every AC from the spec must appear in the verification table
- FAIL verdicts must have specific evidence (not "seems wrong")
- Blocking Issues and Feedback for Developer sections must be present
  even if empty (write "None")
- Verdict must be exactly APPROVED or CHANGES_REQUESTED (all caps)
