"""Slim host-stats sidecar.

Tiny FastAPI server that exposes a single ``/stats`` endpoint with a
sanitised allowlist of host metrics. Reads from ``/proc``, ``/sys``, and
``/etc/os-release`` (mounted read-only by docker compose) and returns
JSON suitable for the metrics tab's ``GET /metrics/stats/slim`` consumer.

The allowlist explicitly excludes anything that could fingerprint the
host or what else runs on it: process list, PIDs, usernames, hostname,
IP/MAC addresses, mount points, network interface names, kernel/OS/CPU-
model strings.

Listens on the internal docker network only (compose binds the port to
the bridge network without a host port). Students cannot reach this
endpoint directly.
"""

from __future__ import annotations

import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import psutil
from fastapi import FastAPI

# Sample state for computing rate metrics. Initialised on startup.
_last_net: dict[str, Any] = {"timestamp": 0.0, "rx": 0, "tx": 0}
_boot_time: float = 0.0


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Initialise rate-metric baselines on startup.

    The ``_app`` parameter is required by FastAPI's lifespan contract
    but unused — we don't store any state on the app instance.
    """
    global _boot_time  # noqa: PLW0603
    _boot_time = psutil.boot_time()
    counters = psutil.net_io_counters()
    _last_net["timestamp"] = time.monotonic()
    _last_net["rx"] = counters.bytes_recv
    _last_net["tx"] = counters.bytes_sent
    yield


app = FastAPI(title="slim-stats-sidecar", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe — no host data exposed."""
    return {"status": "ok"}


@app.get("/stats")
async def stats() -> dict[str, dict[str, Any]]:
    """Return the sanitised allowlist of host stats.

    All output fields are aggregates — no per-process, per-mount, per-
    interface, or per-cpu detail that would enable fingerprinting.
    """
    # CPU
    cpu_pct = psutil.cpu_percent(interval=None)
    load_1m, load_5m, load_15m = os.getloadavg()
    cpu_count = psutil.cpu_count(logical=True) or 0

    # Memory
    mem = psutil.virtual_memory()

    # Disk — root only, aggregated
    disk = psutil.disk_usage("/")

    # Network — aggregated rate over the interval since last poll
    counters = psutil.net_io_counters()
    now = time.monotonic()
    elapsed = now - _last_net["timestamp"]
    if elapsed > 0:
        rx_rate = int((counters.bytes_recv - _last_net["rx"]) / elapsed)
        tx_rate = int((counters.bytes_sent - _last_net["tx"]) / elapsed)
    else:
        rx_rate = 0
        tx_rate = 0
    _last_net["timestamp"] = now
    _last_net["rx"] = counters.bytes_recv
    _last_net["tx"] = counters.bytes_sent

    # Uptime
    uptime_sec = int(time.time() - _boot_time)

    return {
        "cpu": {
            "utilization_pct": round(cpu_pct, 1),
            "load_1m": round(load_1m, 2),
            "load_5m": round(load_5m, 2),
            "load_15m": round(load_15m, 2),
            "core_count": cpu_count,
        },
        "mem": {
            "used_mb": int((mem.total - mem.available) / 1024 / 1024),
            "total_mb": int(mem.total / 1024 / 1024),
        },
        "disk": {
            "used_gb": round(disk.used / 1024 / 1024 / 1024, 2),
            "total_gb": round(disk.total / 1024 / 1024 / 1024, 2),
        },
        "net": {
            "rx_bytes_per_sec": rx_rate,
            "tx_bytes_per_sec": tx_rate,
        },
        "host": {
            "uptime_sec": uptime_sec,
        },
    }
