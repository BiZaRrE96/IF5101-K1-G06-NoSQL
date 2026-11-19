"""Read/write use cases shared by the API and the worker.

Reads join the normalized collections on every request. Filters on related
collections become ID sets inside the cache loader, so a cache HIT skips them.
Names and children are looked up only for the rows of the page, with one
$in query per collection (never one query per row).
"""
from . import cache, config
from .db import clean, get_db
from .schema import Filter, TypeSpec


# ---- helpers --------------------------------------------------------------

def _projection(spec: TypeSpec) -> dict:
    # Mongo _id and personal data are never read into the response.
    return {"_id": 0, **{f: 0 for f in spec.private_fields}}


def _public(spec: TypeSpec, doc: dict) -> dict:
    """Public shape: the <type>_id value becomes `id`, other fields keep their SQL names."""
    doc = dict(doc)
    item_id = doc.pop(spec.id_field)
    return clean({"id": item_id, **doc})


def _pick(doc: dict, keys: tuple) -> dict:
    return {k: doc.get(k) for k in keys}


def _by_id(db, collection: str, id_field: str, ids, fields=("nama",)) -> dict:
    """One $in query: {id: row} for the given ids, returning only the listed fields."""
    ids = list({i for i in ids if i})
    if not ids:
        return {}
    proj = {"_id": 0, id_field: 1, **{f: 1 for f in fields}}
    return {r[id_field]: r for r in db[collection].find({id_field: {"$in": ids}}, proj)}


def _olahraga_by_owner(db, link_coll: str, owner_field: str, owner_ids, extra=()) -> dict:
    """{owner_id: [{olahraga_id, nama, ...extra}]} from a link collection, two queries total."""
    links = list(db[link_coll].find({owner_field: {"$in": list(owner_ids)}}, {"_id": 0}))
    names = _by_id(db, "olahraga", "olahraga_id", {link["olahraga_id"] for link in links})
    out: dict = {}
    for link in links:
        entry = {
            "olahraga_id": link["olahraga_id"],
            "nama": names.get(link["olahraga_id"], {}).get("nama"),
            **{f: link.get(f) for f in extra},
        }
        out.setdefault(link[owner_field], []).append(entry)
    for entries in out.values():
        entries.sort(key=lambda e: e["nama"] or "")
    return out


# ---- enrichment: adds display names to each row (list page or detail) -----

def _enrich_fasilitas(db, rows: list) -> None:
    kel = _by_id(db, "kelurahan", "kelurahan_id", {r.get("kelurahan_id") for r in rows},
                 ("kecamatan_id", "nama"))
    kec = _by_id(db, "kecamatan", "kecamatan_id", {k.get("kecamatan_id") for k in kel.values()})
    olah = _olahraga_by_owner(db, "fasilitas_olahraga", "fasilitas_id",
                              [r["fasilitas_id"] for r in rows], extra=("jumlah_lapangan",))
    for r in rows:
        k = kel.get(r.get("kelurahan_id"), {})
        r["kecamatan_id"] = k.get("kecamatan_id")
        r["nama_kelurahan"] = k.get("nama")
        r["nama_kecamatan"] = kec.get(k.get("kecamatan_id"), {}).get("nama")
        r["olahraga"] = olah.get(r["fasilitas_id"], [])


def _enrich_atlet(db, rows: list) -> None:
    kec = _by_id(db, "kecamatan", "kecamatan_id", {r.get("kecamatan_domisili_id") for r in rows})
    org = _by_id(db, "organisasi", "organisasi_id", {r.get("organisasi_id") for r in rows})
    olah = _olahraga_by_owner(db, "atlet_olahraga", "atlet_id", [r["atlet_id"] for r in rows])
    for r in rows:
        r["nama_kecamatan"] = kec.get(r.get("kecamatan_domisili_id"), {}).get("nama")
        r["nama_organisasi"] = org.get(r.get("organisasi_id"), {}).get("nama")
        r["olahraga"] = olah.get(r["atlet_id"], [])


def _enrich_event(db, rows: list) -> None:
    olah = _by_id(db, "olahraga", "olahraga_id", {r.get("olahraga_id") for r in rows})
    org = _by_id(db, "organisasi", "organisasi_id", {r.get("organisasi_id") for r in rows})
    fas = _by_id(db, "fasilitas", "fasilitas_id", {r.get("fasilitas_id") for r in rows})
    for r in rows:
        r["nama_olahraga"] = olah.get(r.get("olahraga_id"), {}).get("nama")
        r["nama_penyelenggara"] = org.get(r.get("organisasi_id"), {}).get("nama")
        r["nama_fasilitas"] = fas.get(r.get("fasilitas_id"), {}).get("nama")


ENRICH = {"fasilitas": _enrich_fasilitas, "atlet": _enrich_atlet, "event": _enrich_event}


# ---- detail-only children -------------------------------------------------

def _detail_fasilitas(db, item_id: str) -> dict:
    jadwal = (db.jadwal_operasional_fasilitas
              .find({"fasilitas_id": item_id}, {"_id": 0, "hari": 1, "jam_buka": 1, "jam_tutup": 1})
              .sort([("hari", 1), ("jam_buka", 1)]))
    return {"jadwal": list(jadwal)}


def _detail_atlet(db, item_id: str) -> dict:
    pres = list(db.prestasi.find({"atlet_id": item_id}, {"_id": 0}).sort("tanggal_perolehan", -1))
    events = _by_id(db, "event", "event_id", {p.get("event_id") for p in pres}, ("nama", "olahraga_id"))
    olah = _by_id(db, "olahraga", "olahraga_id", {e.get("olahraga_id") for e in events.values()})
    rows = []
    for p in pres:
        ev = events.get(p.get("event_id"), {})
        rows.append({
            "nama_event": ev.get("nama"),
            "nama_olahraga": olah.get(ev.get("olahraga_id"), {}).get("nama"),
            **_pick(p, ("nomor_pertandingan", "peringkat", "medali", "tanggal_perolehan")),
        })
    return {"prestasi": rows}


def _detail_event(db, item_id: str) -> dict:
    pres = list(db.prestasi.find({"event_id": item_id}, {"_id": 0}).sort("peringkat", 1))
    atlet = _by_id(db, "atlet", "atlet_id", {p.get("atlet_id") for p in pres})  # name only, no PII
    rows = [{
        "nama_atlet": atlet.get(p.get("atlet_id"), {}).get("nama"),
        **_pick(p, ("nomor_pertandingan", "peringkat", "medali", "tanggal_perolehan")),
    } for p in pres]
    return {"prestasi": rows,
            "jumlah_atlet_terdaftar": db.event_atlet.count_documents({"event_id": item_id})}


DETAIL_EXTRAS = {"fasilitas": _detail_fasilitas, "atlet": _detail_atlet, "event": _detail_event}


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
    def load() -> dict:
        db = get_db()
        coll = db[spec.collection]
        query = _mongo_query(criteria)
        total = coll.count_documents(query)
        rows = list(coll.find(query, _projection(spec))
                    .sort(list(spec.sort) + [(spec.id_field, 1)])  # unique tie-breaker
                    .skip((page - 1) * size)
                    .limit(size))
        ENRICH[spec.name](db, rows)
        items = [clean({"id": r[spec.id_field], **{c.field: r.get(c.field) for c in spec.columns}})
                 for r in rows]
        return {"items": items, "total": total, "page": page, "page_size": size}

    def key() -> str:
        return cache.list_key(spec.name, cache.current_version(spec.name), normalized, page, size)

    return cache.cached(key, config.CACHE_TTL_LIST, load)


def get_detail(spec: TypeSpec, item_id: str) -> tuple[dict | None, str]:
    def load() -> dict | None:
        db = get_db()
        doc = db[spec.collection].find_one({spec.id_field: item_id}, _projection(spec))
        if doc is None:
            return None  # a missing record is returned as None and not cached
        ENRICH[spec.name](db, [doc])
        out = _public(spec, doc)
        out.update(clean(DETAIL_EXTRAS[spec.name](db, item_id)))
        return out

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
