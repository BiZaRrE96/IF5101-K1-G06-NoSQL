"""Read/write use cases shared by the API and the worker.

Reads join the normalized collections on every cache miss, with one MongoDB
aggregation (queries.py) that returns the finished page or record; lists also
count the matches for paging. Filters on related collections become ID sets
inside the cache loader, so a cache HIT skips them.
"""
from . import cache, config, queries
from .db import clean, get_db
from .schema import Filter, TypeSpec


# ---- helpers --------------------------------------------------------------

def _public(spec: TypeSpec, doc: dict) -> dict:
    """Public shape: the <type>_id value becomes `id` (first), other fields keep their SQL names."""
    doc = dict(doc)
    item_id = doc.pop(spec.id_field)
    return clean({"id": item_id, **doc})


# ---- filters -> MongoDB query (runs inside the cache loader) --------------

def _clause(f: Filter, value) -> dict:
    if f.kind == "date_from":
        return {f.field: {"$gte": value}}
    if f.kind == "date_to":
        return {f.field: {"$lte": value}}
    return {f.field: value}


def _mongo_query(criteria: list) -> dict:
    db = get_db()
    clauses = []
    for f, value in criteria:
        if f.via:
            # Related filter: resolve the value to ids of the link collection first.
            coll, match_field, return_field = f.via
            ids = db[coll].distinct(return_field, {match_field: value})
            clauses.append({f.field: {"$in": ids}})
        else:
            clauses.append(_clause(f, value))
    return {"$and": clauses} if clauses else {}


# ---- use cases ------------------------------------------------------------

def list_page(spec: TypeSpec, criteria: list, normalized: dict, page: int, size: int) -> tuple[dict, str]:
    version = None  # set by key(); stays None when the cache is off or Redis is down

    def key() -> str:
        nonlocal version
        version = cache.current_version(spec.name)
        return cache.list_key(spec.name, version, normalized, page, size)

    def load() -> dict:
        db = get_db()
        coll = db[spec.collection]
        query = _mongo_query(criteria)

        def count() -> int:
            return coll.count_documents(query)

        # The total is shared by every page of this filter: cached once per
        # version, so page 2, 3, ... skip the count. Fixed TTL, not refreshed on read.
        if version is None:
            total = count()
        else:
            total, _ = cache.cached(cache.count_key(spec.name, version, normalized),
                                    config.CACHE_TTL_LIST, count)
        items = list(coll.aggregate(queries.LIST[spec.name](query, (page - 1) * size, size)))
        return {"items": clean(items), "total": total, "page": page, "page_size": size}

    return cache.cached(key, config.CACHE_TTL_LIST, load)


def get_detail(spec: TypeSpec, item_id: str) -> tuple[dict | None, str]:
    def load() -> dict | None:
        db = get_db()
        docs = list(db[spec.collection].aggregate(queries.DETAIL[spec.name](item_id)))
        if not docs:
            return None  # a missing record is returned as None and not cached
        return _public(spec, docs[0])

    return cache.cached(cache.entity_key(spec.name, item_id), config.CACHE_TTL_DETAIL, load)


def filter_options(spec: TypeSpec) -> tuple[dict, str]:
    def load() -> dict:
        db = get_db()
        out = []
        for f in spec.filters:
            item = {"param": f.param, "label": f.label, "kind": f.kind}
            if f.kind == "enum":
                item["options"] = [{"value": v, "label": v} for v in f.choices]
            elif f.kind == "distinct":
                values = sorted(v for v in db[spec.collection].distinct(f.field) if isinstance(v, str))
                item["options"] = [{"value": v, "label": v} for v in values]
            elif f.kind == "ref":
                id_field = f"{f.ref}_id"
                rows = db[f.ref].find({}, {"_id": 0, id_field: 1, "nama": 1}).sort("nama", 1)
                item["options"] = [{"value": r[id_field], "label": r.get("nama", r[id_field])} for r in rows]
            out.append(item)
        return {"type": spec.name, "filters": out}

    return cache.cached(cache.filters_key(spec.name), config.CACHE_TTL_FILTERS, load)


def update(spec: TypeSpec, item_id: str, changes: dict) -> dict | None:
    """Write path: MongoDB first, then invalidate Redis.

    Only the whitelisted fields are set; no audit field is added, because the
    team export has no timestamps. Returns the same shape as the detail view.
    """
    result = get_db()[spec.collection].update_one({spec.id_field: item_id}, {"$set": changes})
    if result.matched_count == 0:
        return None
    cache.invalidate(spec.name, item_id)
    value, _ = get_detail(spec, item_id)
    return value
