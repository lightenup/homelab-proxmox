# A freshly created LXC fails its own network check — cold-create race

**Status**: Backlog — found 2026-09-21 running spec `065`'s T048 (destroy and rebuild).
**Impact**: the **first** deploy of any service fails intermittently. Re-running succeeds with
no change. Shared orchestrator code, so this is not specific to `hermes`.

## What happens

`pve-service-deploy` verifies the new container is reachable after Terraform creates it:

```
ERROR: network check failed: 192.168.1.221 is unreachable
       (ping -c 1 -W 5 returned non-zero)
```

The container was created correctly and was reachable moments later. From the run's own
evidence pack:

```
--- ip route ---
default via 192.168.1.1 dev eth0 onlink
192.168.1.0/24 dev eth0 proto kernel scope link src 192.168.1.221
--- pct config net ---
net0: name=eth0,bridge=vmbr0,gw=192.168.1.1,...,ip=192.168.1.221/24,type=veth
```

Nothing is misconfigured. The check simply runs before a booting container answers ICMP.

## Why it hides

`ping -c 1 -W 5` is **one** attempt with no retry, and it only runs on a **cold create** — a
redeploy targets an already-running container that answers instantly. Every Hermes deploy on
2026-09-21 passed this check; the rebuild-from-nothing did not. It is a race, not a hard
failure: the container's first deploy that same morning won it, this one lost it.

So the failure appears exclusively in the situation where it is least welcome — the first
deploy of a new service, or a disaster-recovery rebuild — and never during the ordinary
redeploys that would have exposed it.

## Fix

Retry with a bounded wait instead of a single probe: poll for reachability for ~60s before
declaring failure. Every other readiness gate in this estate already works that way — the
Ansible role's own `wait_for` and `uri` steps use `retries`/`until`, and the deploy's later
stages are patient. This one check is the outlier.

A single `ping` is also a weak liveness signal for what the script actually needs next, which
is SSH. Polling the SSH port would test the thing that matters rather than a proxy for it.

## Evidence

- Failing run: `lab-hermes-unknown-20260921-104439`, apply exit 1 after 54s
- Immediate re-run with **no change**: success, 65 tasks, 30 changed, 0 failed
- Container was `running` with correct networking throughout
