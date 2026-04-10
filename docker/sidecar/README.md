# `docker/sidecar/` — slim host-stats sidecar

Tiny container that runs alongside the app on slim and exposes a single
`/stats` HTTP endpoint **on the internal docker network only** (never on
the host port).

## Why a sidecar

The app container is hardened: `read_only`, no host mounts, `cap_drop: ALL`.
That means it can't see `/proc` or `/sys` of the host machine. The sidecar
has read-only mounts of `/proc`, `/sys`, and `/etc/os-release` and exposes
a sanitized allowlist of host stats: CPU util, load averages, memory
used/total, disk used/total, network rx/tx bytes/sec, uptime.

## Sanitization allowlist

Explicitly **excluded** from the response:

- Process list, PIDs, usernames, command lines
- Hostname, fully-qualified domain name
- IP addresses, MAC addresses
- Mount points, disk device names
- Network interface names
- Kernel version, OS version strings, CPU model strings
- Container names

Explicitly **included**:

- GPU data (when applicable — not on slim, which has no discrete GPU)
- Aggregate CPU/RAM/disk/net counters
- Load averages
- Uptime seconds

## Guapo equivalent

None. Per instructor decision, guapo is not patched to add a `/v1/stats`
endpoint. The observability module uses indirect inference from the frozen
surface (`/healthz`, health RTT stddev, last chat TTFT, etc.) instead.
