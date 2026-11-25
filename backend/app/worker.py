"""Maintenance worker (one-shot commands, same image as the API).

    python -m app.worker ping               check MongoDB and Redis
    python -m app.worker ensure-indexes     create the indexes of the normalized collections (idempotent)
    python -m app.worker warm               pre-fill filter options and first list pages
    python -m app.worker flush-cache        delete this app's Redis keys (not FLUSHDB)
    python -m app.worker bench [runs]       time the essential reads, MISS vs HIT (default 20 runs)
"""
import statistics
import sys
import time

from . import cache, config, service
from .db import get_db
from .schema import TYPES, parse_filters

# Unique natural keys: (collection, field).
UNIQUE_INDEXES = [
    ("fasilitas", "fasilitas_id"),
    ("atlet", "atlet_id"),
    ("event", "event_id"),
    ("prestasi", "prestasi_id"),
    ("kecamatan", "kecamatan_id"),
    ("kelurahan", "kelurahan_id"),
    ("olahraga", "olahraga_id"),
    ("organisasi", "organisasi_id"),
    ("jadwal_operasional_fasilitas", "jadwal_id"),
]

# Secondary indexes for filters, sorts and joins: (collection, key pattern).
INDEXES = [
    ("jadwal_operasional_fasilitas", [("fasilitas_id", 1), ("hari", 1)]),
    ("fasilitas_olahraga", [("olahraga_id", 1)]),
    ("fasilitas_olahraga", [("fasilitas_id", 1)]),
    ("atlet_olahraga", [("olahraga_id", 1)]),
    ("atlet_olahraga", [("atlet_id", 1)]),
    ("kelurahan", [("kecamatan_id", 1)]),
    ("prestasi", [("atlet_id", 1)]),
    ("prestasi", [("event_id", 1)]),
    ("event_atlet", [("event_id", 1)]),
    ("fasilitas", [("nama", 1), ("fasilitas_id", 1)]),
    ("fasilitas", [("kelurahan_id", 1)]),
    ("fasilitas", [("kategori", 1)]),
    ("fasilitas", [("status_operasional", 1)]),
    ("fasilitas", [("kondisi_fisik", 1)]),
    ("fasilitas", [("jenis_akses", 1)]),
    ("atlet", [("nama", 1), ("atlet_id", 1)]),
    ("atlet", [("kecamatan_domisili_id", 1)]),
    ("atlet", [("organisasi_id", 1)]),
    ("atlet", [("jenis_kelamin", 1)]),
    ("atlet", [("status_binaan", 1)]),
    ("event", [("tanggal_mulai", -1), ("nama", 1), ("event_id", 1)]),
    ("event", [("olahraga_id", 1)]),
    ("event", [("organisasi_id", 1)]),
    ("kecamatan", [("nama", 1)]),
    ("olahraga", [("nama", 1)]),
    ("organisasi", [("nama", 1)]),
    ("organisasi", [("nama", 1), ("organisasi_id", 1)]),
    ("organisasi", [("kelurahan_id", 1)]),
    ("organisasi", [("jenis_organisasi", 1)]),
    ("organisasi_olahraga", [("olahraga_id", 1)]),
    ("organisasi_olahraga", [("organisasi_id", 1)]),
]


def ping() -> int:
    get_db().command("ping")
    print("mongo: ok")
    print(f"redis: {'ok' if cache.ping() else 'down'} (CACHE_ENABLED={config.CACHE_ENABLED})")
    return 0


def ensure_indexes() -> int:
    db = get_db()
    for coll, field in UNIQUE_INDEXES:
        db[coll].create_index([(field, 1)], unique=True)
    for coll, keys in INDEXES:
        db[coll].create_index(keys)
    print(f"ensured {len(UNIQUE_INDEXES)} unique and {len(INDEXES)} secondary indexes")
    return 0


def warm() -> int:
    if not config.CACHE_ENABLED:
        print("CACHE_ENABLED=false, nothing to warm")
        return 0
    for spec in TYPES.values():
        service.filter_options(spec)
        service.list_page(spec, [], {}, 1, config.DEFAULT_PAGE_SIZE)
        print(f"{spec.name}: warmed")
    return 0


def flush_cache() -> int:
    print(f"removed {cache.flush_app_keys(TYPES.keys())} keys")
    return 0


# ---- bench ----------------------------------------------------------------

def _list_call(type_name: str, params: dict):
    spec = TYPES[type_name]
    criteria, normalized = parse_filters(spec, params)
    return lambda: service.list_page(spec, criteria, normalized, 1, config.DEFAULT_PAGE_SIZE)


def _detail_call(type_name: str, item_id: str):
    spec = TYPES[type_name]
    return lambda: service.get_detail(spec, item_id)


def _scenarios(db) -> list[tuple[str, object | None]]:
    """(name, call) pairs; call is None when the seed has no matching data."""
    kec = db.kecamatan.find_one({}, {"_id": 0, "kecamatan_id": 1}, sort=[("nama", 1)])
    link = db.fasilitas_olahraga.find_one({}, {"_id": 0, "olahraga_id": 1})
    fas = db.fasilitas.find_one({}, {"_id": 0, "fasilitas_id": 1}, sort=[("nama", 1), ("fasilitas_id", 1)])
    atlet = db.prestasi.find_one({}, {"_id": 0, "atlet_id": 1})
    event = db.event.find_one({}, {"_id": 0, "event_id": 1},
                              sort=[("tanggal_mulai", -1), ("nama", 1), ("event_id", 1)])
    org = db.organisasi.find_one({}, {"_id": 0, "organisasi_id": 1}, sort=[("nama", 1), ("organisasi_id", 1)])
    return [
        ("fasilitas list, no filter, p1",
         _list_call("fasilitas", {})),
        ("fasilitas list, kecamatan + aktif",
         _list_call("fasilitas", {"kecamatan_id": kec["kecamatan_id"], "status_operasional": "aktif"})
         if kec else None),
        ("fasilitas list, olahraga",
         _list_call("fasilitas", {"olahraga_id": link["olahraga_id"]}) if link else None),
        ("fasilitas detail",
         _detail_call("fasilitas", fas["fasilitas_id"]) if fas else None),
        ("atlet list, perempuan + binaan",
         _list_call("atlet", {"jenis_kelamin": "perempuan", "status_binaan": "binaan"})),
        ("atlet detail (with prestasi)",
         _detail_call("atlet", atlet["atlet_id"]) if atlet else None),
        ("event list, no filter, p1",
         _list_call("event", {})),
        ("event detail",
         _detail_call("event", event["event_id"]) if event else None),
        ("organisasi list, no filter",
         _list_call("organisasi", {})),
        ("organisasi detail",
         _detail_call("organisasi", org["organisasi_id"]) if org else None),
    ]


def _measure(call, runs: int, flush: bool) -> tuple[list[float], list[str]]:
    """Time `runs` calls. With flush=True this app's keys are deleted before each call (not timed)."""
    times, statuses = [], []
    for _ in range(runs):
        if flush:
            cache.flush_app_keys(TYPES.keys())
        start = time.perf_counter()
        _, status = call()
        times.append((time.perf_counter() - start) * 1000)
        statuses.append(status)
    return times, statuses


def _p95(values: list[float]) -> float:
    return values[0] if len(values) < 2 else statistics.quantiles(values, n=20, method="inclusive")[-1]


def _check(name: str, statuses: list[str], expected: str) -> None:
    if set(statuses) != {expected}:
        print(f"WARNING {name}: expected X-Cache {expected}, got {sorted(set(statuses))}", file=sys.stderr)


def bench(runs: int = 20) -> int:
    runs = max(1, runs)
    enabled = config.CACHE_ENABLED
    db = get_db()
    print(f"Bench: {runs} runs per scenario, CACHE_ENABLED={enabled}, times in ms\n")
    if enabled:
        print("| scenario | miss mean ms | miss p50 | miss p95 | hit mean ms | hit p50 | hit p95 | speedup (miss mean / hit mean) |")
        print("|---|---:|---:|---:|---:|---:|---:|---:|")
    else:
        print("| scenario | miss (BYPASS) mean ms | p50 | p95 |")
        print("|---|---:|---:|---:|")

    for name, call in _scenarios(db):
        if call is None:
            print(f"| {name} | skipped: no matching data | | | | | | |", flush=True)
            continue
        # MISS: keys are flushed before each run when the cache is on.
        miss_t, miss_s = _measure(call, runs, flush=enabled)
        miss_mean, miss_p50, miss_p95 = statistics.mean(miss_t), statistics.median(miss_t), _p95(miss_t)
        if not enabled:
            _check(name, miss_s, "BYPASS")
            print(f"| {name} | {miss_mean:.1f} | {miss_p50:.1f} | {miss_p95:.1f} |", flush=True)
            continue
        _check(name, miss_s, "MISS")
        # HIT: one warm-up call fills the cache, then timed calls read it.
        call()
        hit_t, hit_s = _measure(call, runs, flush=False)
        _check(name, hit_s, "HIT")
        hit_mean = statistics.mean(hit_t)
        speedup = miss_mean / hit_mean if hit_mean > 0 else float("inf")
        print(f"| {name} | {miss_mean:.1f} | {miss_p50:.1f} | {miss_p95:.1f} "
              f"| {hit_mean:.1f} | {statistics.median(hit_t):.1f} | {_p95(hit_t):.1f} | {speedup:.1f}x |",
              flush=True)
    return 0


COMMANDS = {"ping": ping, "ensure-indexes": ensure_indexes, "warm": warm, "flush-cache": flush_cache}

if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "bench" and len(args) <= 2:
        sys.exit(bench(int(args[1]) if len(args) == 2 else 20))
    if len(args) != 1 or args[0] not in COMMANDS:
        print(__doc__)
        sys.exit(2)
    sys.exit(COMMANDS[args[0]]())
