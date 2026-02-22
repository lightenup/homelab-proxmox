# Review Task

Review the implementation for the current feature against the specification.

## Instructions

1. Run `.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks`
   from the repository root to discover the feature directory and available docs.

2. Load these artifacts (all paths relative to the feature directory):
   - `spec.md` — the source of truth for requirements
   - `plan.md` — the intended design
   - `tasks.md` — the implementation checklist
   - `.specify/memory/constitution.md` — process principles
   - `.specify/memory/addendum.md` — tech constraints (if present)

3. Run the project's test gate using `adapter/test-config.sh`:
   ```bash
   source adapter/test-config.sh
   run_project_tests
   run_project_lint
   ```
   If `test-config.sh` is unconfigured (returns warning), fall back to
   detecting the test command from `plan.md`, Makefile, package.json, or
   project files.

4. For each user story in `spec.md`, check whether the implementation satisfies
   its acceptance criteria. Examine the actual source code — do not rely solely
   on test results.

5. Verify all task checkboxes in `tasks.md` are marked `[X]`.

6. Check that `spec.md` and `plan.md` have NOT been modified during implementation
   (they should be unchanged from the plan/tasks stage).

7. Write your review to `FEATURE_DIR/review.md` following the exact format
   specified in your persona instructions.

8. If the verdict is `CHANGES_REQUESTED`, ensure the "Feedback for Developer"
   section contains precise, actionable instructions referencing specific files,
   functions, or task IDs.

## Important

- Do NOT modify any source code, tests, or spec artifacts.
- Do NOT modify `tasks.md` checkboxes.
- Only produce `review.md` as output.
