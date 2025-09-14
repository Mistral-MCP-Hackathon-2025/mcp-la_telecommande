"""Networking helpers for quick reachability checks."""

from __future__ import annotations

import socket
import time


def tcp_reachable(host: str, port: int, timeout: float = 3.0) -> tuple[bool, float | None, str | None]:
    """Attempt a TCP connection and measure latency.

    Returns:
        (reachable, latency_ms, reason)
    """
    start = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            elapsed_ms = (time.monotonic() - start) * 1000.0
            return True, round(elapsed_ms, 2), None
    except Exception as e:
        return False, None, str(e)
