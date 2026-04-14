"""Client for the slim host-stats sidecar.

The sidecar runs in the same docker compose as the app container, exposing
its sanitised allowlist of host stats on the internal docker network only
(never on the host port). This client polls it from the app and returns
:class:`SlimHostStats` snapshots for the metrics tab.

The sidecar URL is configured via env (``SLIM_SIDECAR_URL``) so the same
code works in dev (where there's no sidecar — the client returns ``None``)
and prod (where the sidecar is at e.g. ``http://stats-sidecar:8080``).
"""

from __future__ import annotations

import os
from typing import Final

from core.observability.records import SlimHostStats

# Default sidecar address on the internal docker network. Overridden via
# env var in compose.
_DEFAULT_SIDECAR_URL: Final[str] = "http://stats-sidecar:8080/stats"
_REQUEST_TIMEOUT_SECONDS: Final[float] = 1.0


class SlimStatsClient:
    """Async client that fetches host stats from the slim sidecar.

    Configured from the ``SLIM_SIDECAR_URL`` env var. If unset, the client
    falls back to a default that points at the canonical compose service
    name. If the env var is explicitly set to an empty string, the client
    operates in disabled mode and returns ``None`` from :meth:`fetch` —
    useful in dev environments where no sidecar is running.
    """

    def __init__(self, sidecar_url: str | None = None) -> None:
        """Construct a client targeting the given sidecar URL.

        Args:
            sidecar_url: Optional override. If ``None``, uses the
                ``SLIM_SIDECAR_URL`` env var or the default. If an empty
                string, disables the client (always returns ``None``).
        """
        if sidecar_url is None:
            sidecar_url = os.environ.get("SLIM_SIDECAR_URL", _DEFAULT_SIDECAR_URL)
        self._sidecar_url = sidecar_url
        self._enabled = bool(sidecar_url)

    @property
    def enabled(self) -> bool:
        """True if the client will attempt sidecar fetches."""
        return self._enabled

    async def fetch(self) -> SlimHostStats | None:
        """Fetch a single snapshot from the sidecar.

        Returns ``None`` if the client is disabled, the sidecar is
        unreachable, or the response is malformed. The caller should treat
        ``None`` as "no host stats available right now" and render an
        appropriate placeholder rather than treating it as an error.
        """
        if not self._enabled:
            return None

        # Lazy import so this module is importable without httpx for tests
        # that don't exercise the network path.
        import httpx

        try:
            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
                resp = await client.get(self._sidecar_url)
                if resp.status_code != 200:
                    return None
                payload = resp.json()
                return _parse_payload(payload)
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return None


def _parse_payload(payload: dict[str, object]) -> SlimHostStats | None:
    """Convert a sidecar JSON response into a :class:`SlimHostStats`.

    Returns ``None`` rather than raising if the payload shape is unexpected,
    so the dashboard degrades gracefully when the sidecar version drifts
    from this client.
    """
    try:
        cpu = payload["cpu"]
        mem = payload["mem"]
        disk = payload["disk"]
        net = payload["net"]
        host = payload.get("host", {})
        if not isinstance(cpu, dict) or not isinstance(mem, dict):
            return None
        if not isinstance(disk, dict) or not isinstance(net, dict):
            return None
        if not isinstance(host, dict):
            return None
        return SlimHostStats(
            cpu_utilization_pct=float(cpu["utilization_pct"]),
            cpu_load_1m=float(cpu.get("load_1m", 0.0)),
            cpu_load_5m=float(cpu.get("load_5m", 0.0)),
            cpu_load_15m=float(cpu.get("load_15m", 0.0)),
            cpu_count=int(cpu.get("core_count", 0)),
            mem_used_mb=int(mem["used_mb"]),
            mem_total_mb=int(mem["total_mb"]),
            disk_used_gb=float(disk["used_gb"]),
            disk_total_gb=float(disk["total_gb"]),
            net_rx_bytes_per_sec=int(net["rx_bytes_per_sec"]),
            net_tx_bytes_per_sec=int(net["tx_bytes_per_sec"]),
            uptime_sec=int(host.get("uptime_sec", 0)),
        )
    except (KeyError, TypeError, ValueError):
        return None
