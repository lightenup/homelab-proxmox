#!/usr/bin/env python3
"""Assert the llm-router gateway does what spec 064 says it does.

This is NOT `scripts/healthcheck/llm-router.sh`. That answers "is the container
up and the endpoint answering", which is necessary and is already covered. This
answers "is the gateway behaving the way the spec claims", which is a different
question and the one the remaining acceptance tasks in
`specs/064-llm-router/tasks.md` are about.

The distinction is load-bearing. On the sibling setup (a LiteLLM gateway on a
Mac, see `local-llm/docs/FINDINGS.md`) the dominant failure mode turned out to be
**configured and inert**: six separate cases where a setting read correctly in
the config file, raised no error at load, and did nothing. Among them was
`context_window_fallbacks`, which is silently dead unless
`enable_pre_call_checks` is also set — precisely the mechanism SC-009 depends on.
This role already sets that flag (`config.yaml.j2:43`), which is why the check
below asserts it *keeps* being set rather than assuming it.

So every check here is labelled by the strength of its evidence:

    obs   a request was sent and the response was examined
    cfg   a file was read

and where a behavioural check is possible it is preferred, because a config file
is a statement of intent and this repo's own handoff notes are full of intent
that had not yet met an LXC.

    ./scripts/healthcheck/llm-router-doctor.py --base-url http://192.168.20.219:4000
    ./scripts/healthcheck/llm-router-doctor.py --profile tailscale --json out.json
    ./scripts/healthcheck/llm-router-doctor.py --list        # what it would check

UNVERIFIED AGAINST LIVE INFRASTRUCTURE. Written on the dev Mac, which Zscaler
keeps off the tailnet, so no check here has ever been observed to fail against a
real gateway. By this repo's own standard that means it has been run, not
tested. Fault-inject each check once on first use — the sibling project found a
check that could never fail while reporting success, and it was the tool built
specifically to catch that class of bug.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
VARS = REPO / "ansible" / "group_vars" / "services" / "vars.yml"
CONFIG_TPL = REPO / "ansible" / "roles" / "llm_router" / "templates" / "config.yaml.j2"

# Which spec clause each check exists to defend. Printed on failure so a red
# result points at the requirement rather than at the script.
@dataclass
class Result:
    name: str
    ok: bool
    kind: str            # "obs" | "cfg"
    ref: str             # SC-/FR- clause
    detail: str = ""
    layer: str = ""


@dataclass
class Doctor:
    base_url: str
    key: str
    timeout: float = 60.0
    results: list[Result] = field(default_factory=list)

    def check(self, layer, name, kind, ref, fn):
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {str(e)[:150]}"
        self.results.append(Result(name, ok, kind, ref, detail, layer))
        print(f"  [{'PASS' if ok else 'FAIL'}] {kind}  {ref:8s} {name:44s} {detail[:64]}")
        return ok

    def post(self, body, timeout=None, key=None):
        req = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/v1/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {key or self.key}"})
        with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
            return json.loads(r.read())

    def get(self, path, timeout=15):
        req = urllib.request.Request(f"{self.base_url.rstrip('/')}{path}",
                                     headers={"Authorization": f"Bearer {self.key}"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode(errors="replace")


def aliases_from_vars() -> list[dict]:
    """Read the declarative alias mapping without needing a YAML dependency.

    FR-003 makes this data rather than role logic, which is what lets the doctor
    derive its checks from the same source the deploy templates from. A parser
    that drifts from the deploy would be worse than no parser, so this only
    extracts the fields it asserts on.
    """
    if not VARS.exists():
        return []
    text = VARS.read_text()
    block = re.search(r"(?ms)^llm_router_aliases:\s*\n(.*?)(?=^\S)", text)
    if not block:
        return []
    out, cur = [], None
    for line in block.group(1).splitlines():
        m = re.match(r"\s*-\s+name:\s*(\S+)", line)
        if m:
            cur = {"name": m.group(1), "deployments": [], "fallback_to": None}
            out.append(cur)
            continue
        if cur is None:
            continue
        m = re.match(r"\s*fallback_to:\s*(\S+)", line)
        if m:
            cur["fallback_to"] = None if m.group(1) == "null" else m.group(1)
        m = re.match(r"\s*-\s+id:\s*(\S+)", line)
        if m:
            cur["deployments"].append({"id": m.group(1)})
        m = re.match(r"\s*tier:\s*(\S+)", line)
        if m and cur["deployments"]:
            cur["deployments"][-1]["tier"] = m.group(1)
        m = re.match(r"\s*api_base:\s*[\"']?(\S+?)[\"']?\s*$", line)
        if m and cur["deployments"]:
            cur["deployments"][-1]["api_base"] = m.group(1)
        # provider_model and context_window are what the residency check asserts against.
        # They were omitted here originally, which left want_models empty and made that
        # check return "nothing to assert" — a PASS it could never not return. Parsing
        # them is what gives the check something to be wrong about.
        m = re.match(r"\s*provider_model:\s*[\"']?(\S+?)[\"']?\s*$", line)
        if m and cur["deployments"]:
            cur["deployments"][-1]["provider_model"] = m.group(1)
        m = re.match(r"\s*context_window:\s*(\d+)\s*$", line)
        if m and cur["deployments"]:
            cur["deployments"][-1]["context_window"] = int(m.group(1))
    return out


# --------------------------------------------------------------------------
# Config layer — cheap, runs anywhere, catches the inert-config class
# --------------------------------------------------------------------------

def check_config(d: Doctor, aliases) -> None:
    print("\nCONFIG — readable without touching the gateway")

    def tpl(pred, label):
        t = CONFIG_TPL.read_text()
        return pred(t), label

    d.check("config", "enable_pre_call_checks is set", "cfg", "SC-009",
            lambda: tpl(lambda t: "enable_pre_call_checks: true" in t,
                        "without it context_window_fallbacks is inert; SC-009 "
                        "would pass review and fail in production"))
    d.check("config", "context_window_fallbacks declared", "cfg", "SC-009",
            lambda: tpl(lambda t: "context_window_fallbacks:" in t, ""))

    def fallbacks_withdrawn():
        # FR-004 is WITHDRAWN (amendment-drop-metered-tiers.md): with no remote
        # tier there is nothing to fall back to, and cross-alias fallback within
        # one host is slower, not safer. Assert the withdrawal actually held —
        # every alias must declare fallback_to null — rather than asserting a
        # `fallbacks:` key that the template emits empty regardless. A check that
        # passes no matter what the config says is the anti-pattern this doctor exists
        # to avoid.
        declared = [a["name"] for a in aliases if a.get("fallback_to")]
        return not declared, ("all aliases fallback=null (FR-004 withdrawn)"
                              if not declared else
                              f"alias still declares a fallback (FR-004 is withdrawn): {declared}")
    d.check("config", "cross-alias fallbacks withdrawn", "cfg", "FR-004",
            fallbacks_withdrawn)

    def no_placeholder():
        if not VARS.exists():
            return False, "group_vars not found"
        bad = [a["name"] for a in aliases for dep in a["deployments"]
               if "<" in dep.get("api_base", "")]
        return not bad, ("all api_base resolved" if not bad
                         else f"UNRESOLVED placeholder in: {bad} — the Mac's "
                              f"MagicDNS name is still unset")
    d.check("config", "no api_base placeholders remain", "cfg", "FR-016",
            no_placeholder)

    def keys_prefixed():
        # LiteLLM rejects virtual keys without the sk- prefix. Confirmed by
        # testing during 064 and recorded in HANDOFF.md; cheap to re-assert.
        env_keys = {k: v for k, v in os.environ.items()
                    if k.startswith("LLM_ROUTER_") and k.endswith("_KEY")
                    or k == "LITELLM_MASTER_KEY"}
        bad = [k for k, v in env_keys.items() if v and not v.startswith("sk-")]
        if not env_keys:
            return True, "no router keys in env to check (running off-box)"
        return not bad, ("all sk- prefixed" if not bad else f"NOT sk-: {bad}")
    d.check("config", "virtual keys carry the sk- prefix", "cfg", "FR-015",
            keys_prefixed)


# --------------------------------------------------------------------------
# Gateway layer — behavioural
# --------------------------------------------------------------------------

def check_gateway(d: Doctor, aliases) -> None:
    print("\nGATEWAY — observed against a live endpoint")

    def reachable():
        st, _ = d.get("/health/liveliness")
        return st == 200, f"HTTP {st}"
    if not d.check("gateway", "endpoint answers", "obs", "SC-004", reachable):
        print("       gateway unreachable — remaining gateway checks skipped")
        return

    for a in aliases:
        def answers(a=a):
            r = d.post({"model": a["name"], "max_tokens": 16,
                        "messages": [{"role": "user", "content": "Reply: ok"}]},
                       timeout=120)
            txt = (r["choices"][0]["message"].get("content") or "").strip()
            return bool(txt), f"served, {len(txt)} chars"
        d.check("gateway", f"alias answers: {a['name']}", "obs", "FR-002", answers)

    def only_aliases():
        # FR-002: a client must not need a provider model ID. If a raw provider
        # ID is also addressable, clients will drift onto it and FR-003's
        # remapping guarantee quietly stops holding.
        try:
            d.post({"model": "claude-sonnet-5", "max_tokens": 8,
                    "messages": [{"role": "user", "content": "hi"}]}, timeout=45)
            return False, "a raw provider model ID was ACCEPTED"
        except urllib.error.HTTPError as e:
            return e.code in (400, 401, 403, 404), f"refused with HTTP {e.code}"
    d.check("gateway", "raw provider model IDs are not addressable", "obs",
            "FR-002", only_aliases)

    def budget_enforces():
        # SC-010. Distinct from the Mac setup, where budgets are inert because
        # local models carry no pricing: here the metered tier has real pricing,
        # so spend accrues and a cap can actually bite.
        st, body = d.get("/key/info")
        if st != 200:
            return False, f"key info unavailable: HTTP {st}"
        info = json.loads(body).get("info", {})
        cap, spend = info.get("max_budget"), info.get("spend")
        if cap is None:
            return False, "calling key has NO max_budget — SC-010 cannot hold"
        return True, f"cap {cap}, spend {spend}"
    d.check("gateway", "calling key carries a budget", "obs", "SC-010",
            budget_enforces)


# --------------------------------------------------------------------------
# Local tier — the Mac, the part that is allowed to be absent
# --------------------------------------------------------------------------

def check_local_tier(d: Doctor, aliases) -> None:
    print("\nLOCAL TIER — the Mac's LiteLLM on the LAN; SC-001 withdrawn, it must fail CLEAN")

    base = next((dep.get("api_base") for a in aliases for dep in a["deployments"]
                 if dep.get("tier") == "local" and dep.get("api_base")), None)
    if not base or "<" in base:
        d.check("local", "local tier api_base resolved", "cfg", "FR-016",
                lambda: (False, "placeholder unresolved — cannot probe the Mac"))
        return

    # base is ".../v1" for an OpenAI-compatible backend; oMLX's health and admin
    # endpoints sit at the root, not under /v1.
    root = base[:-3].rstrip("/") if base.rstrip("/").endswith("/v1") else base.rstrip("/")

    def mac_gateway_reachable():
        # The Mac now runs LiteLLM in front of oMLX, so the probe is LiteLLM's
        # liveness endpoint, not oMLX's /health. oMLX is not LAN-reachable at
        # all by design (FR-016) and cannot be probed from here.
        try:
            with urllib.request.urlopen(f"{root}/health/liveliness", timeout=10) as r:
                return r.status == 200, f"HTTP {r.status}"
        except Exception as e:
            # Not a gateway failure. SC-001 requires this to be survivable, and
            # the replacement Mac is a laptop that leaves the LAN by design.
            return False, (f"unreachable ({type(e).__name__}) — SC-001 says "
                           f"the gateway must still serve every alias")
    d.check("local", "Mac LiteLLM reachable on the LAN", "obs", "FR-016",
            mac_gateway_reachable)

    def aliases_resolve(aliases=aliases):
        """Each hermes alias must resolve to a Mac role alias that answers.

        Residency can no longer be observed from here. oMLX is bound to
        127.0.0.1 behind the Mac's LiteLLM (FR-016), so /admin/api/models is
        unreachable and the pinning check that lived here cannot run. It moved
        to the Mac side of RUNBOOK § 1 rather than being silently dropped — a
        check that cannot reach its subject must be removed, not left returning
        a pass.
        """
        want = [dep.get("provider_model", "").split("/", 1)[-1]
                for a in aliases for dep in a["deployments"]
                if dep.get("tier") == "local"]
        if not want:
            return False, "no local deployments declared — the mapping is empty"
        try:
            req = urllib.request.Request(f"{root}/v1/models",
                                         headers={"Authorization": f"Bearer {d.key}"})
            with urllib.request.urlopen(req, timeout=15) as r:
                have = {m["id"] for m in json.loads(r.read()).get("data", [])}
        except Exception as e:
            return False, f"cannot list the Mac's models: {type(e).__name__}"
        missing = [w for w in want if w not in have]
        return not missing, (f"all {len(want)} map onto Mac aliases: {','.join(want)}"
                             if not missing else
                             f"hermes alias points at a Mac alias that does not exist: {missing}")
    d.check("local", "every alias maps onto a live Mac role alias", "obs", "FR-016",
            aliases_resolve)

    print("       note: SC-001 is WITHDRAWN. With no remote tier the requirement is "
          "that every\n       alias FAILS CLEAN when the Mac is away — an error naming the "
          "backend, never a\n       hang. Powering the Mac off (T035) is still the only way "
          "to exercise it, and is\n       still a different failure mode from a stopped "
          "LiteLLM (T034).")


LAYERS = {"config": check_config, "gateway": check_gateway, "local": check_local_tier}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default=os.environ.get(
        "LLM_ROUTER_URL", "http://192.168.20.219:4000"))
    ap.add_argument("--key", default=os.environ.get("LLM_ROUTER_CANARY_KEY", ""))
    ap.add_argument("--layer", choices=sorted(LAYERS), action="append")
    ap.add_argument("--json", help="write results here")
    ap.add_argument("--list", action="store_true",
                    help="print the checks and their spec refs, run nothing")
    args = ap.parse_args()

    aliases = aliases_from_vars()
    if args.list:
        print("checks derive from ansible/group_vars/services/vars.yml:")
        for a in aliases:
            tiers = ",".join(d.get("tier", "?") for d in a["deployments"])
            print(f"  alias {a['name']:18s} -> [{tiers}]  fallback={a['fallback_to']}")
        return 0

    if not aliases:
        print("WARNING: no aliases parsed from group_vars — checks will be thin",
              file=sys.stderr)

    d = Doctor(base_url=args.base_url, key=args.key)
    print("=" * 78)
    print(f"llm-router doctor — {args.base_url}")
    print("obs = a request was sent and examined; cfg = a file was read")
    print("=" * 78)
    for name in (args.layer or list(LAYERS)):
        LAYERS[name](d, aliases)

    fails = [r for r in d.results if not r.ok]
    obs = sum(1 for r in d.results if r.kind == "obs")
    print("\n" + "=" * 78)
    print(f"  {len(d.results) - len(fails)}/{len(d.results)} pass "
          f"({obs} observed, {len(d.results) - obs} config-only)")
    if fails:
        print("\n  FAILURES, with the clause each defends:")
        for r in fails:
            print(f"    {r.ref:8s} [{r.layer}] {r.name}\n             {r.detail}")
    if args.json:
        Path(args.json).write_text(json.dumps(
            {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "base_url": args.base_url,
             "results": [r.__dict__ for r in d.results]}, indent=2))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
