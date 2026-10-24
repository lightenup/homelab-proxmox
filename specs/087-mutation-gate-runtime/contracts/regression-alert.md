# Contract: regression alert (ntfy publisher `mutation`)

A publisher under [`082`'s publisher contract](../../082-ntfy-push-service/contracts/publisher-interface.md).

## Account

| Field | Value |
|---|---|
| account | `mutation` |
| topic | `mutation` (new; one publisher per topic) |
| vault | `ntfy_mutation_token`, `ntfy_mutation_password_hash` in `ansible/group_vars/services/vault.yml` |
| onboarding | `docs/runbooks/ntfy-add-publisher.md`: role defaults entry, vault, deploy ntfy, subscribe |

## When it fires

Only from `nightly-deeper-verification.yml`, only when the gate script exited 1 (below the gate).
Exit 2 (run failed) fails the job without a message: the red nightly and GitHub's failure email
cover it. PR runs never publish.

## Request

```text
POST https://ntfy.hus-sky.no/mutation
Authorization: Bearer <ntfy_mutation_token>
Title: Mutation score 58.40% is below 60.00%
Priority: high
Tags: test_tube
Click: <URL of the nightly run>

Floor 61.00% (margin 1.00). Commit 9d80372.
killed 1650 · survived 1128 · no tests 1337
Most survivors:
312 orchestrator
188 service_lifecycle
140 cli
 97 ops_cli
 61 inventory
```

- The body is plain text, under 1 KB, built from `report.json`. The top 5 modules come from
  `survivors_by_module`.
- The token comes from vault on the runner, is masked with `::add-mask::`, and goes only in the
  header.

## Delivery failure

If the response is not `200`, or the connection fails, the step logs
`::warning::Regression alert not delivered (<status or error>)`. The job is already failing because
of the score, and stays failed.
