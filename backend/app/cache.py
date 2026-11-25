"""Redis cache-aside layer.

Enabled by default (CACHE_ENABLED=true). Key names follow ARCHITECTURE.md
section 6, which keeps the naming convention of the NoSQL KV composite-key
proposal.

Every Redis failure falls back to MongoDB: the cache can make reads faster,
never make them fail.
"""
import hashlib
import json
import logging
import time
from typing import Callable

import redis

from . import config

log = logging.getLogger("dispora.cache")

_client: redis.Redis | None = None

# Circuit breaker: after a Redis failure, reads skip Redis for this many
# seconds instead of paying the connect timeout (and Docker DNS delay) on
# every request.
DOWN_SECONDS = 10
_down_until = 0.0


def _redis_down() -> bool:
    return time.monotonic() < _down_until


def _mark_down(exc: Exception, what: str) -> None:
    global _down_until
    _down_until = time.monotonic() + DOWN_SECONDS
    log.warning("redis %s failed, skipping Redis for %ss: %s", what, DOWN_SECONDS, exc)


def client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(
            config.REDIS_URL, decode_responses=True,
            socket_timeout=0.5, socket_connect_timeout=0.5,
        )
    return _client


# ---- key builders ---------------------------------------------------------

def entity_key(type_name: str, item_id: str) -> str:
    return f"{type_name}:{item_id}"                     # e.g. fasilitas:{F}


def version_key(type_name: str) -> str:
    return f"ver:{type_name}"                           # list-cache generation


def filters_key(type_name: str) -> str:
    return f"filters:{type_name}"                       # dropdown options


def _filter_digest(normalized: dict) -> str:
    return hashlib.sha1(json.dumps(normalized, sort_keys=True).encode()).hexdigest()[:16]


def list_key(type_name: str, version: int, normalized: dict, page: int, size: int) -> str:
    return f"list:{type_name}:v{version}:{_filter_digest(normalized)}:p{page}:s{size}"


def count_key(type_name: str, version: int, normalized: dict) -> str:
    # Total for one filter, shared by all its pages; same version as the list pages.
    return f"count:{type_name}:v{version}:{_filter_digest(normalized)}"


# ---- operations -----------------------------------------------------------

def ping() -> bool:
    try:
        return bool(client().ping())
    except redis.RedisError:
        return False


def current_version(type_name: str) -> int:
    return int(client().get(version_key(type_name)) or 0)


def cached(key: str | Callable[[], str], ttl: int, loader: Callable[[], dict | None]) -> tuple[dict | None, str]:
    """Return (value, status) where status is HIT, MISS, BYPASS or ERROR.

    A loader result of None (for example a missing record) is returned but
    never cached, so a record created later is visible immediately.
    """
    if not config.CACHE_ENABLED:
        return loader(), "BYPASS"
    if _redis_down():
        return loader(), "ERROR"
    try:
        resolved = key() if callable(key) else key
        hit = client().get(resolved)
        if hit is not None:
            return json.loads(hit), "HIT"
    except redis.RedisError as exc:
        _mark_down(exc, "read")
        return loader(), "ERROR"
    value = loader()
    if value is None:
        return None, "MISS"
    try:
        client().set(resolved, json.dumps(value), ex=ttl)
    except redis.RedisError as exc:
        _mark_down(exc, "write")
    return value, "MISS"


def invalidate(type_name: str, item_id: str | None = None, also: tuple[str, ...] = ()) -> None:
    """Call AFTER the MongoDB write succeeded.

    Deletes the entity key and bumps list generations so every cached list
    page for those types becomes unreachable (old pages expire by TTL).
    """
    if not config.CACHE_ENABLED:
        return
    try:
        pipe = client().pipeline()
        if item_id:
            pipe.delete(entity_key(type_name, item_id))
        for t in (type_name, *also):
            pipe.incr(version_key(t))
        pipe.execute()
    except redis.RedisError as exc:
        # Stale entries now live until their TTL; log loudly.
        log.error("cache invalidation failed for %s:%s: %s", type_name, item_id, exc)


def flush_app_keys(type_names) -> int:
    """Delete only keys owned by this app (never FLUSHDB)."""
    patterns = ["list:*", "count:*", "filters:*", "ver:*", *[f"{t}:*" for t in type_names]]
    removed = 0
    r = client()
    for pattern in patterns:
        batch = []
        for key in r.scan_iter(match=pattern, count=500):
            batch.append(key)
            if len(batch) >= 500:
                removed += r.delete(*batch)
                batch = []
        if batch:
            removed += r.delete(*batch)
    return removed
