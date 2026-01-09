# Research: Terraform plan JSON destructive classification + bounded summaries

## Goal
Produce a **simple, robust** algorithm (and `jq` shape) for:
- `destructive: true|false` where destructive means **replace or destroy**
- plan change **counts**
- a **bounded** (truncated) list of changed resources for GitHub job summaries

This should match the repo’s existing `jq`-based `blast-radius.json` approach in [scripts/lab/pve-service-deploy](../../scripts/lab/pve-service-deploy).

## Terraform JSON fields to rely on
From `terraform show -json <planfile>`:
- `.resource_changes[]?` is the authoritative list of **planned actions**.
  - Each item has:
    - `.address` (string; stable for display and scoping)
    - `.change.actions` (array of strings)
- `.change.actions` values commonly seen:
  - `["no-op"]` (ignore)
  - `["create"]`
  - `["update"]`
  - `["delete"]`
  - `["create","delete"]` (create_before_destroy replacement)
  - `["delete","create"]` (delete_then_create replacement)
  - `["read"]` (typically data sources; not apply-destructive)

Optional / version-dependent (do not hard-require):
- `.resource_drift[]?` (drift detected during refresh; may be present in newer Terraform)
- `.output_changes` (not resources; generally should not affect destructive gating)

## Best-practice classification rules
### 1) “Destructive”
Treat a plan as destructive if **any** planned resource change is a destroy or a replace:
- **Destroy**: `.change.actions == ["delete"]`
- **Replace**: `.change.actions` contains both `"create"` and `"delete"` (order irrelevant)

This correctly handles both:
- `delete_then_create` (`["delete","create"]`)
- `create_before_destroy` (`["create","delete"]`)

### 2) Counts
Compute counts over `.resource_changes[]?` excluding `no-op`.
Recommended minimal buckets (matches existing repo contract):
- `create`: actions exactly `["create"]`
- `update`: actions exactly `["update"]`
- `destroy`: actions exactly `["delete"]`
- `replace`: actions contains both `create` and `delete` (either order)

Optionally (nice for observability but not required for gating):
- `read`: actions exactly `["read"]`
- `other`: anything else non-`no-op` (future-proofing)

### 3) Drift-only / refresh-only edge cases
Key point: the **apply blast radius** should be based on `.resource_changes`.

- If you run `terraform plan -refresh-only`, you may still get `resource_changes` (often `update`). Those are still “planned changes” and should be counted.
- If Terraform emits `.resource_drift`, treat it as **informational** (separate counters) so you can say “drift detected” without confusing it with “will apply changes”.
- Do **not** mark destructive due to drift-only metadata unless it is also present as a planned destroy/replace in `.resource_changes`.

### 4) Large plans
Avoid dumping full `.resource_changes` lists into job summaries and/or evidence that will be rendered in UI.
Recommended approach:
- Always compute totals over **all** resource changes.
- Show only the first `N` resource addresses in severity order:
  1) destroy
  2) replace
  3) update
  4) create
- Include `resources_total`, `resources_shown`, and `truncated: true|false`.

This keeps summaries bounded while staying audit-friendly (full plan JSON remains in evidence).

## A simple robust `jq` algorithm (aligned to current `blast-radius.json`)
Below is a pattern that matches the existing logic in `compute_blast_radius` but adds truncation + optional drift counters.

```jq
# Inputs (as jq --argjson limit 50 etc.)

def is_noop: (.change.actions == ["no-op"]);

def is_replace: ((.change.actions | index("create")) and (.change.actions | index("delete")));

def class:
  if .change.actions == ["create"] then "create"
  elif .change.actions == ["update"] then "update"
  elif .change.actions == ["delete"] then "destroy"
  elif is_replace then "replace"
  elif .change.actions == ["read"] then "read"
  else "other" end;


def severity:
  if class == "destroy" then 0
  elif class == "replace" then 1
  elif class == "update" then 2
  elif class == "create" then 3
  else 4 end;

# Planned changes
(.resource_changes // [])
| map(select(is_noop | not)) as $rcs
| {
    counts: {
      create: ($rcs | map(select(.change.actions == ["create"])) | length),
      update: ($rcs | map(select(.change.actions == ["update"])) | length),
      replace: ($rcs | map(select(is_replace)) | length),
      destroy: ($rcs | map(select(.change.actions == ["delete"])) | length)
    },
    destructive: (
      ($rcs | map(select(.change.actions == ["delete"] or is_replace)) | length) > 0
    ),
    resources_total: ($rcs | length),
    resources: (
      $rcs
      | map({address: .address, actions: .change.actions, class: class})
      | sort_by(severity, .address)
      | .[0:$limit]
    )
  }
| .resources_shown = (.resources | length)
| .truncated = (.resources_shown < .resources_total)

# Optional drift-only info (safe if missing)
| .drift = ((.resource_drift // [])
    | map(select(.change.actions != ["no-op"]))
    | {
        total: length,
        destroy: (map(select(.change.actions == ["delete"])) | length),
        replace: (map(select(((.change.actions|index("create")) and (.change.actions|index("delete"))))) | length),
        update: (map(select(.change.actions == ["update"])) | length),
        create: (map(select(.change.actions == ["create"])) | length)
      }
  )
```

### Notes on robustness
- Uses `(.resource_changes // [])` to tolerate missing keys.
- Replacement is detected by `index("create")` + `index("delete")` (order-agnostic).
- Keeps “destructive” tightly scoped to replace/destroy, matching **FR-005** in this spec.

## Recommendation (what to implement)
- Keep `blast-radius.json` semantics as-is for gating:
  - `destructive := any destroy OR replace`
  - counts over `.resource_changes`
- For workflow UI summaries, add a bounded “summary view” derived from the same plan JSON:
  - counts + destructive + confirmation token
  - `resources_total`, `resources_shown`, `truncated`
  - a severity-sorted list of up to `N` addresses
- Treat `.resource_drift` as informational-only (separate counters), not as a destructive trigger.

---

# Research: GitHub Actions summaries + annotations

## Decision
Use a combination of:

- `$GITHUB_STEP_SUMMARY` (bounded Markdown “dashboard” per job)
- targeted annotations (`::error`, `::warning`, `::notice`) for root-cause visibility

## Rationale
- Operators should be able to understand the plan/failure without downloading artifacts.
- Job summary size is bounded; using a truncated resource list prevents run UI spam.
- Annotations make failures obvious and actionable, without requiring log spelunking.

## Implementation notes
- Prefer a final summary step guarded by `if: always()` so summaries render even when earlier steps fail.
- Limit each summary to well under 1 MiB; keep only top-level counts + first N resources.
- Avoid workflow-command injection when printing untrusted content; never `toJson(github)` or print secrets.

---

# Research: Enforcing “apply uses exact planned bytes”

## Decision
Enforce that PROD apply uses the exact planfile produced by Plan(PROD) by:

- passing a specific plan RUN_ID from plan → apply
- applying the planfile at `reports/plan/plan.tfplan` from that RUN_ID
- verifying plan metadata matches (service/env) and that the planfile exists (fail fast if not)

## Rationale
- Prevents “re-plan drift” where apply differs from the reviewed/approved plan.
- Fits existing repo architecture: evidence packs on PVE already contain `plan.tfplan` + `plan.json` + `blast-radius.json`.

## Alternatives considered
- **GitHub Actions artifact as the source-of-truth planfile**: strongest binding, but may increase artifact size/retention concerns.
- **Always re-plan at apply**: simplest implementation, but violates FR-014 and undermines approval quality.

## Expected failure modes (desired)
- State drift between plan and apply should cause apply to fail and instruct the operator to re-plan.
- Missing planfile or mismatched metadata should fail immediately with clear operator guidance.
