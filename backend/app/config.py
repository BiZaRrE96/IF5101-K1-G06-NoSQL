"""Runtime settings, read once from environment variables."""
import os


def _bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:57017")
MONGO_DB = os.getenv("MONGO_DB", "dispora")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
# Set CACHE_ENABLED=false to bypass Redis entirely (every response is X-Cache: BYPASS).
CACHE_ENABLED = _bool("CACHE_ENABLED", "true")
CACHE_TTL_DETAIL = int(os.getenv("CACHE_TTL_DETAIL", "3600"))
CACHE_TTL_LIST = int(os.getenv("CACHE_TTL_LIST", "300"))
CACHE_TTL_FILTERS = int(os.getenv("CACHE_TTL_FILTERS", "3600"))

# Empty token disables the write endpoints entirely.
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
