# `core/ops/` — instructor-only operations dashboard

Locked. **Instructor-only.** Mounted at `/ops`, gated by a separate Cloudflare
Access policy that whitelists only the instructor's email.

Students cannot see this, cannot edit it, and shouldn't even know the URL.

## What it shows

A live SSE event stream of everything the instructor needs to monitor during
the 2.5-hour class session:

- PR lifecycle events from GitHub webhooks (opened, updated, merged)
- Each agent's check results on each PR (pass/fail + link)
- Deploy events (start, health check, success, rollback)
- Egress firewall drops (from `docker/firewall/audit_drops.sh`)
- Agent 9 malice alerts (high severity, visually distinct)
- Chat errors in the app container (tail of `docker logs`)
- Guapo load indicators (queue signal, health RTT, last TTFT)
- Slim host load (CPU, RAM, disk aggregates)

## Visual design

- Green / yellow / red row severity coloring
- Red banner + browser audio cue on high-severity events
- No database — in-memory ring buffer of ~500 events
- Refresh forgets; there's an append-only JSON dump for post-class review

## Kill switches

POST form buttons for fast response during class:

| Button | What it does |
|---|---|
| Pause agent inference proxy | 503s all CI LLM calls, frees guapo for student traffic |
| Pause deploys | Halts the `deploy-on-main` workflow mid-flight |
| Panic stop app | Takes the app container down |
| Reload firewall | Reapplies the nftables egress allow-list |

## Co-monitoring with Claude

`/ops/events.json` is a machine-readable endpoint with a service-token auth
path, so a Claude Code session open during class can `curl` the same event
stream the instructor is watching. That way the human and the assistant see
the same reality in real time and can triage together.
