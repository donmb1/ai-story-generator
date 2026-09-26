"""Geräte-Token und einfache In-Memory-Rate-Limits."""

from __future__ import annotations

import hashlib
import hmac
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from .settings import settings


def token_from(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    # Fallback für alte BusyBox-wget ohne --header
    return request.headers.get("x-device-token") or request.query_params.get("t", "")


def check_token(request: Request) -> str:
    """Gibt eine nicht umkehrbare Geräte-ID für Logs und Rate-Limits zurück."""
    if not settings.device_token:
        raise HTTPException(503, "DEVICE_TOKEN not configured")
    token = token_from(request)
    if not token or not hmac.compare_digest(token.encode(), settings.device_token.encode()):
        raise HTTPException(401, "unauthorized")
    return hashlib.sha256(token.encode()).hexdigest()[:8]


class SlidingWindow:
    def __init__(self, limit: int, window_s: int):
        self.limit, self.window = limit, window_s
        self.hits: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True


requests_limit = SlidingWindow(settings.requests_per_minute, 60)
stories_limit = SlidingWindow(settings.stories_per_hour, 3600)
# Nur eine Story-Erzeugung gleichzeitig pro Gerät (Doppel-Tap, Retry)
generating: set[str] = set()
generating_lock = threading.Lock()
