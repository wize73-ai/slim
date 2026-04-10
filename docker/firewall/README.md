# `docker/firewall/` — nftables egress allow-list

Applied to the app container's network namespace on slim. This is the
**load-bearing line of defense** that limits what malicious or broken
student code can do after deploy.

## What's in here

- `setup.sh` — applies the nftables ruleset on slim boot. Idempotent.
- `rules.nft` — the actual allow-list rules.
- `audit_drops.sh` — continuously tails the netfilter drop log and
  forwards events to the instructor ops dashboard event stream.

## The allow-list

```
ALLOW out → <guapo Tailscale IP>:8000    (inference)
ALLOW out → cloudflared sidecar          (for inbound tunneling)
ALLOW out → 127.0.0.1:53                 (stub DNS)
DROP   out → everywhere else             (logged)
```

## What this stops

Even if all 9 pre-merge agents miss something, code running in the app
container **cannot**:

- Phone home to an attacker server
- Open a reverse shell
- Scan the instructor's LAN for other targets
- Exfiltrate data over HTTP, DNS, or any other egress
- Reach GHCR or any registry at runtime (only deploy-time pulls are
  allowed, and those happen on slim outside the container's netns)
- Download additional payloads
- Mine cryptocurrency profitably (even if a miner runs, it can't connect
  to a pool)

## Strict mode

Toggleable via env var `FIREWALL_STRICT_MODE=1`. When set, the first
drop event halts the container immediately and flags red on the ops
dashboard. Default off, recommended on during live class sessions.
