#!/usr/bin/env python3
"""Post-build smoke test for the wize73 app container.

Used by:

* ``.github/workflows/pr-07-build-and-smoke.yml`` (agent 7) — runs after
  every PR's image is built, before the PR can merge.
* ``deploy.sh`` on slim — runs against the freshly-pulled image during
  blue/green deployment.
* The pre-class dry-run in task #20.

The script:

1. Starts the container with ``OPENAI_BASE_URL`` pointing at a mock so
   the chat handler doesn't try to reach guapo.
2. Polls ``/healthz`` until ready (or 30s timeout).
3. Hits the locked ``/metrics/healthz``, ``/metrics/``, ``/metrics/turns``
   endpoints to verify the metrics tab is mounted and responsive — this
   is the gate that catches "a student PR somehow broke the locked tab".
4. Hits ``/ops/healthz`` (unauthenticated liveness) to verify the ops
   sub-app is mounted.
5. Stops and removes the container.

Returns exit code 0 on success, non-zero on any failure.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any

DEFAULT_IMAGE = "wize73-app:smoke-test"
DEFAULT_CONTAINER_NAME = "wize73-app-smoke"
DEFAULT_HOST_PORT = 18080
HEALTH_TIMEOUT_SECONDS = 30
MOCK_OPENAI_URL = "http://127.0.0.1:9999/v1"  # unreachable on purpose


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a shell command and return the completed process."""
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def docker_run(image: str, name: str, host_port: int) -> str:
    """Start the container in detached mode and return its container id."""
    print(f"==> starting {image} as {name} on host port {host_port}")
    # Stop any leftover container with the same name from a prior run.
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    result = run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "-p",
            f"{host_port}:8080",
            "-e",
            f"OPENAI_BASE_URL={MOCK_OPENAI_URL}",
            "-e",
            "OPENAI_API_KEY=sk-test",
            "-e",
            "SLIM_SIDECAR_URL=",  # disabled for smoke
            image,
        ]
    )
    return result.stdout.strip()


def docker_logs(name: str) -> None:
    """Print the container's logs to stderr for debugging."""
    print("==> container logs:", file=sys.stderr)
    result = subprocess.run(["docker", "logs", name], capture_output=True, text=True)
    print(result.stdout, file=sys.stderr)
    print(result.stderr, file=sys.stderr)


def docker_stop(name: str) -> None:
    """Stop and remove the container."""
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)


def fetch(url: str, timeout: float = 5.0) -> tuple[int, dict[str, Any] | str]:
    """GET a URL and return (status_code, parsed_body).

    Body is a parsed JSON dict if the content-type is application/json,
    otherwise the raw text.
    """
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            body = resp.read().decode("utf-8")
            ctype = resp.headers.get("content-type", "")
            if "application/json" in ctype:
                return status, json.loads(body)
            return status, body
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def wait_for_health(host_port: int, timeout: int) -> bool:
    """Poll /healthz until 200 or timeout."""
    url = f"http://127.0.0.1:{host_port}/healthz"
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        try:
            status, body = fetch(url, timeout=2.0)
            if status == 200:
                print(f"    /healthz ok: {body}")
                return True
        except (urllib.error.URLError, ConnectionError):
            pass
        time.sleep(1.0)
    return False


def smoke_test(image: str, name: str, host_port: int) -> int:
    """Run the full smoke test sequence. Returns exit code."""
    cid = docker_run(image, name, host_port)
    print(f"    container id: {cid[:12]}")

    failures: list[str] = []
    try:
        # 1. Wait for the app to come up.
        print("==> waiting for /healthz")
        if not wait_for_health(host_port, HEALTH_TIMEOUT_SECONDS):
            docker_logs(name)
            return 2

        base = f"http://127.0.0.1:{host_port}"

        checks = [
            ("/healthz", 200),
            ("/metrics/healthz", 200),
            ("/metrics/", 200),
            ("/metrics/turns", 200),
            ("/metrics/stats/slim", 200),  # available=False since sidecar is disabled
            ("/ops/healthz", 200),
        ]

        for path, expected_status in checks:
            print(f"==> GET {path}")
            try:
                status, body = fetch(f"{base}{path}")
            except Exception as e:
                failures.append(f"{path} threw {type(e).__name__}: {e}")
                continue
            if status != expected_status:
                failures.append(f"{path} returned {status}, expected {expected_status}")
                if isinstance(body, str):
                    print(f"    body: {body[:200]}")
                continue
            print(f"    ✓ {status}")

        # Verify the metrics tab actually contains the expected token-flow chart
        # markers — guards against a PR that nukes the locked template.
        print("==> verifying /metrics/ contains the locked tab markers")
        status, body = fetch(f"{base}/metrics/")
        if status == 200 and isinstance(body, str):
            required_markers = [
                "Token flow by turn",
                "Projection calculator",
                'href="/metrics/turns"',  # raw JSON link
            ]
            for marker in required_markers:
                if marker not in body:
                    failures.append(f"/metrics/ missing marker: {marker!r}")
            if not any(f.startswith("/metrics/ missing marker") for f in failures):
                print("    ✓ all locked markers present")
        else:
            failures.append(f"/metrics/ returned {status}, can't verify markers")

    finally:
        if failures:
            docker_logs(name)
        docker_stop(name)

    if failures:
        print("\n✗ SMOKE TEST FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print("\n✓ SMOKE TEST PASSED")
    return 0


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--name", default=DEFAULT_CONTAINER_NAME)
    parser.add_argument("--port", type=int, default=DEFAULT_HOST_PORT)
    args = parser.parse_args()
    return smoke_test(args.image, args.name, args.port)


if __name__ == "__main__":
    sys.exit(main())
