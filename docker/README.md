# `docker/` — container build and deploy infrastructure

Locked. **Students cannot edit.** If you think a Dockerfile needs to change,
open an issue.

## What lives here

| Path | What it is |
|---|---|
| `app/` | Dockerfile for the main chatbot app. |
| `sidecar/` | Dockerfile for the host-stats sidecar on slim. |
| `agent-proxy/` | Dockerfile for the agent inference proxy (CI → slim → guapo). |
| `firewall/` | nftables egress allow-list setup and audit scripts. |
| `smoke_test.py` | Post-build smoke test used by agent 7 and the pre-class dry run. |

## Hardening

All containers run with:

- `read_only: true` rootfs
- `tmpfs` for `/tmp`
- `cap_drop: [ALL]`
- `no-new-privileges: true`
- Non-root user
- No host paths mounted
- No Docker socket mounted
- Resource caps (cpus, memory, pids_limit)

## Network

The app container's network namespace has an nftables egress allow-list
applied by `firewall/setup.sh`. It permits only:

- Guapo's Tailscale IP on port 8000
- `cloudflared` sidecar (for inbound tunneling)
- Localhost stub DNS

Everything else is dropped and logged. Dropped packets feed the instructor
ops dashboard event stream.

## Build and deploy

`deploy-on-main.yml` builds the image on push to `main`, tags with commit SHA
plus `latest`, pushes to GHCR, then SSHes to slim via Tailscale and runs
`deploy.sh` (which lives on the box, not in the repo). `deploy.sh` does
blue/green with a `/healthz` gate and auto-rollback on health failure within
30 seconds. The last 5 image tags stay on slim for arbitrary rollback.
