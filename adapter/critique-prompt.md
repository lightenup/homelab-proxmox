# Self-Critique Pass

You have just produced an artifact for this project. Now critically review
your own output as if you were a senior peer reviewer.

## What to evaluate

1. **Completeness** — Does the artifact cover all requirements from the
   constitution, addendum, and user input? Are there gaps?
2. **Consistency** — Does it align with existing specs, plans, or prior
   artifacts? Are there contradictions?
3. **Specificity** — Are statements concrete and actionable, or vague and
   hand-wavy? Could a developer implement from this without guessing?
4. **Risks & Assumptions** — Are assumptions documented? Are edge cases
   and failure modes addressed?
5. **Structure** — Does the artifact follow the expected format and use
   clear, well-organized sections?

## Output format

Write your critique as a markdown section. Be specific — cite the exact
part of the artifact that needs improvement and explain why.

If the artifact is strong, say so briefly and note only minor improvements.

```markdown
## Self-Critique

### Strengths
- (what's good)

### Issues Found
- **[severity: high|medium|low]** (description of issue and suggested fix)

### Verdict
REVISE | ACCEPT
```

If verdict is ACCEPT, the artifact will be used as-is.
If verdict is REVISE, your critique will be fed back as context for a
second pass to address the issues you identified.
