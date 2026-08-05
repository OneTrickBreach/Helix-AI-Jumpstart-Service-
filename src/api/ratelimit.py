"""Rate limiting for the conversational endpoints (Iteration 5 Phase 5).

Why this exists: a chat box is the one surface on this box that a viewer can drive
in a loop, and `/chat/whatif` spends real optimizer time. Without a limit, a stuck
UI or an impatient click could keep the GPU busy in the middle of a demo — and
`fresh=true` deliberately bypasses the result cache, so "it was cached" is not a
defence.

Two different protections, because they answer two different questions:

**A sliding window, always keyed on the caller's address.** This is what actually
protects the box: it cannot be escaped by rotating a client-supplied id.

**A max-runs cap keyed on the session,** which is what the plan of action asks for.
It bounds one browser tab's total optimizer runs, so a runaway component cannot
grind through a demo. A fresh tab gets a fresh budget, which is the right trade for
a single-user prototype: the window above is still in force either way.

Both are in-process and per-container, which is honest for a single-node PoC and
explicitly not a distributed rate limiter. Unlike the what-if caches, this one *is*
lock-protected — FastAPI runs sync endpoints in a threadpool, so two concurrent
requests really do share this state.

**What this is not.** The caller's address comes from the proxy headers that our own
nginx sets, so a client that talks straight to the API — which needs the API key —
could forge them and get a fresh bucket each time. This is a runaway-load guard for a
single-user demo, not an anti-abuse control against an authenticated attacker: anyone
holding the key can already call the endpoint in a loop. Real per-tenant quotas belong
to the production track (Iteration 6) along with the rest of multi-tenant isolation.
"""

from __future__ import annotations

import os
import re
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import HTTPException, Request


SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{4,64}$")


def _int_env(name: str, default: int) -> int:
    """A positive integer from the environment, or the default.

    A malformed or non-positive value falls back to the default rather than
    silently disabling the limit — "0 means unlimited" is exactly the kind of
    configuration accident that turns a guardrail off without anyone noticing.
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


@dataclass(frozen=True)
class Limit:
    """`max_events` in `window_seconds`, per caller."""

    name: str
    max_events: int
    window_seconds: int

    @property
    def human(self) -> str:
        return f"{self.max_events} per {self.window_seconds}s"


def limits() -> dict[str, Limit]:
    """The configured limits. Defaults are sized for a live demo, not for load.

    A grounded question is cheap (no optimizer, ~2-4 s of local model time), so its
    allowance is generous. A confirmed what-if runs the real pipeline twice, so it
    is not.
    """
    window = _int_env("HELIX_CHAT_RATE_WINDOW_SECONDS", 60)
    return {
        "ask": Limit("ask", _int_env("HELIX_CHAT_MAX_ASKS", 30), window),
        "light": Limit("light", _int_env("HELIX_CHAT_MAX_LIGHT", 60), window),
        "run": Limit("run", _int_env("HELIX_CHAT_MAX_RUNS", 10), window),
    }


def max_runs_per_session() -> int:
    return _int_env("HELIX_CHAT_MAX_RUNS_PER_SESSION", 40)


# What the caller was doing, in words, for the refusal message. "Too many run
# requests" is not a sentence anyone should read on a demo screen.
BUCKET_LABELS = {
    "ask": "questions",
    "light": "requests",
    "run": "what-if runs",
}


class SlidingWindowLimiter:
    """Timestamps per (limit, key), pruned to the window on every check."""

    def __init__(self) -> None:
        self._events: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._totals: dict[tuple[str, str], int] = defaultdict(int)
        self._lock = threading.Lock()

    def check_and_record(self, limit: Limit, key: str, now: float | None = None) -> int:
        """Record one event and return how many remain, or raise ``RateLimited``."""
        moment = time.monotonic() if now is None else now
        with self._lock:
            bucket = self._events[(limit.name, key)]
            cutoff = moment - limit.window_seconds
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit.max_events:
                retry_after = max(1, int(bucket[0] + limit.window_seconds - moment) + 1)
                raise RateLimited(limit, key, retry_after)
            bucket.append(moment)
            self._totals[(limit.name, key)] += 1
            return limit.max_events - len(bucket)

    def total(self, limit_name: str, key: str) -> int:
        with self._lock:
            return self._totals[(limit_name, key)]

    def bump_total(self, counter: str, key: str) -> int:
        """Increment a plain lifetime counter (the per-session run cap uses this)."""
        with self._lock:
            self._totals[(counter, key)] += 1
            return self._totals[(counter, key)]

    def reset(self) -> None:
        with self._lock:
            self._events.clear()
            self._totals.clear()


class RateLimited(Exception):
    def __init__(self, limit: Limit, key: str, retry_after: int) -> None:
        super().__init__(f"{limit.name} limit of {limit.human} reached")
        self.limit = limit
        self.key = key
        self.retry_after = retry_after


LIMITER = SlidingWindowLimiter()


def reset_limits() -> None:
    """Clear all state. For tests and for an operator restarting a demo."""
    LIMITER.reset()


def client_key(request: Request) -> str:
    """Who to count against: the caller's address, as seen through the proxy.

    Deliberately not the client-supplied session id: an id the caller chooses can be
    rotated, so keying the window on it would make the window decorative.
    """
    forwarded = request.headers.get("x-forwarded-for") or ""
    address = (
        request.headers.get("x-real-ip")
        or forwarded.split(",")[0].strip()
        or (request.client.host if request.client else "")
        or "unknown"
    )
    return f"ip:{address}"


def session_key(session_id: str | None) -> str | None:
    """A validated session id, or None when the caller did not supply a usable one."""
    if not session_id or not SESSION_ID_PATTERN.match(session_id):
        return None
    return f"session:{session_id}"


def enforce(
    request: Request,
    bucket: str,
    session_id: str | None = None,
    counts_as_run: bool = False,
) -> dict[str, str]:
    """Apply the window (and the per-session run cap), or raise HTTP 429.

    Returns headers describing what is left, so a client can behave well rather than
    discovering the limit by being refused.
    """
    configured = limits()[bucket]
    session = session_key(session_id)

    if counts_as_run and session is not None:
        cap = max_runs_per_session()
        used = LIMITER.total("run_session", session)
        if used >= cap:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"This session has run {used} what-if{'' if used == 1 else 's'}, which is the "
                    f"per-session cap of {cap}. Reload the page to start a new session, or raise "
                    "HELIX_CHAT_MAX_RUNS_PER_SESSION on the server. Nothing was run."
                ),
            )

    try:
        remaining = LIMITER.check_and_record(configured, client_key(request))
    except RateLimited as exc:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Too many {BUCKET_LABELS.get(bucket, bucket)}: the limit is {exc.limit.human} from one "
                f"caller. Try again in about {exc.retry_after}s. Nothing was run."
            ),
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc

    headers = {
        "X-RateLimit-Limit": str(configured.max_events),
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Window-Seconds": str(configured.window_seconds),
    }
    if counts_as_run and session is not None:
        # Counted only once the window check has passed, so a request that was
        # refused does not consume the session's budget.
        used = LIMITER.bump_total("run_session", session)
        headers["X-RateLimit-Session-Runs-Remaining"] = str(max(0, max_runs_per_session() - used))
    return headers


__all__ = [
    "LIMITER",
    "Limit",
    "RateLimited",
    "SlidingWindowLimiter",
    "client_key",
    "enforce",
    "limits",
    "max_runs_per_session",
    "reset_limits",
    "session_key",
]
