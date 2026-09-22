# `PasswordAuthentication yes` is left on across the estate — inert today, one `passwd` from live

**Status**: Backlog — found 2026-09-21 running spec `065`'s T042 against `hermes`.
**Impact**: none today, and that is the whole problem. The protection currently rests on
*"no account happens to have a password set"* rather than on configuration, so it is one
ordinary administrative action away from silently disappearing.

## What was measured

On `hermes` (192.168.1.221), `sshd -T`:

```
permitrootlogin without-password
pubkeyauthentication yes
passwordauthentication yes        # <-- global, and not what the spec assumes
kbdinteractiveauthentication no
permitemptypasswords no
```

The server therefore advertises password as an available method:

```
$ ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no root@192.168.1.221
root@192.168.1.221: Permission denied (publickey,password).
```

Root itself is safe — `permitrootlogin without-password` refuses a password for root
regardless. And no account can be logged into with a password today, because **no account has
a usable password hash**: every entry in `/etc/shadow` is `*` or `!`. The accounts with a login
shell are `root`, `ansible` and `sync`.

So the practical exposure is nil, and T042's *behavioural* clause passes.

## Why it is still worth fixing

The configuration does not encode the intent. `passwd ansible`, or any future role or template
that sets a password, turns on password-authenticated SSH for that account **with no other
change and no signal**. Nothing in the repo asserts the property, so nothing would catch it.

It is also not Hermes-specific — this is the Proxmox Debian template default, so every LXC in
the estate almost certainly carries it. Checked on `hermes` only; the others are assumed, not
verified.

## Direction, not verified

`PasswordAuthentication no` in a drop-in (`/etc/ssh/sshd_config.d/`) applied by whatever common
role already touches every service LXC, plus an assertion so it cannot regress. Two things to
confirm before doing it:

1. **Whether anything depends on password auth** — the `pi-runner` and `synology` hosts use
   non-root users and are outside the `services` group; they need checking separately rather
   than being swept up.
2. **Console access remains the recovery path** — `pct enter` from the PVE host does not go
   through sshd, so locking out password SSH cannot lock the owner out of the box. Worth
   stating explicitly in the change, because "disable password auth" is the kind of change that
   looks risky and gets deferred for the wrong reason.

Cheap, estate-wide, and it converts an accident waiting to happen into an invariant.
