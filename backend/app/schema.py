"""Public data types: list columns, whitelisted filters and editable fields.

Field names are the SQL column names of the normalized MongoDB collections
(one collection per SQL table, `_id` never exposed, the natural key is
`<type>_id`). Code lists come from SQL Bab 3 (CHECK constraints).
Only this file and queries.py know MongoDB collection and field paths.
"""
import re
from dataclasses import dataclass, field
from datetime import date

STATUS_OPERASIONAL = ("aktif", "tidak_aktif", "beralih_fungsi", "perlu_verifikasi_ulang", "perlu_survei_fisik")
KONDISI_FISIK = ("baik", "cukup", "kurang_layak", "rusak")
JENIS_AKSES = ("gratis", "berbayar", "campuran", "anggota")
JENIS_EVENT = ("kompetisi", "turnamen", "latihan", "festival", "lainnya")
TINGKAT = ("kecamatan", "kota", "provinsi", "nasional", "internasional")
STATUS_EVENT = ("rencana", "berlangsung", "selesai", "dibatalkan")
JENIS_KELAMIN = ("laki_laki", "perempuan")
STATUS_BINAAN = ("binaan", "non_binaan", "purna_binaan")
JENIS_ORGANISASI = ("koni", "cabor", "klub", "komunitas", "yayasan", "sekolah", "rt", "rw",
                    "karang_taruna", "instansi_pemerintah", "perusahaan", "lainnya")

ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class FilterError(ValueError):
    pass


@dataclass(frozen=True)
class Filter:
    param: str            # query-string name
    label: str
    kind: str             # enum | distinct | ref | bool | date_from | date_to
    field: str            # field on the type's own collection
    choices: tuple = ()   # enum only
    ref: str = ""         # ref only: collection of the options (value <ref>_id, label nama)
    # Related filter: (collection, match_field, return_field). The value is first
    # turned into ids: distinct(return_field, {match_field: value}), then the
    # main query uses field $in ids. Resolved by service.py.
    via: tuple = ()


@dataclass(frozen=True)
class Column:
    field: str
    label: str


@dataclass
class TypeSpec:
    name: str
    label: str
    collection: str
    columns: tuple
    filters: tuple
    sort: tuple
    editable: dict = field(default_factory=dict)  # field -> tuple of choices | "nonneg_int"

    @property
    def id_field(self) -> str:
        return f"{self.name}_id"    # public id, e.g. fasilitas_id


TYPES: dict[str, TypeSpec] = {
    "fasilitas": TypeSpec(
        name="fasilitas",
        label="Fasilitas",
        collection="fasilitas",
        columns=(
            Column("nama", "Nama"),
            Column("kategori", "Kategori"),
            Column("olahraga", "Olahraga"),
            Column("nama_kecamatan", "Kecamatan"),
            Column("nama_kelurahan", "Kelurahan"),
            Column("status_operasional", "Status"),
            Column("kondisi_fisik", "Kondisi"),
            Column("jenis_akses", "Akses"),
        ),
        filters=(
            Filter("kecamatan_id", "Kecamatan", "ref", "kelurahan_id", ref="kecamatan",
                   via=("kelurahan", "kecamatan_id", "kelurahan_id")),
            Filter("olahraga_id", "Olahraga", "ref", "fasilitas_id", ref="olahraga",
                   via=("fasilitas_olahraga", "olahraga_id", "fasilitas_id")),
            Filter("kategori", "Kategori", "distinct", "kategori"),
            Filter("status_operasional", "Status operasional", "enum", "status_operasional", STATUS_OPERASIONAL),
            Filter("kondisi_fisik", "Kondisi fisik", "enum", "kondisi_fisik", KONDISI_FISIK),
            Filter("jenis_akses", "Jenis akses", "enum", "jenis_akses", JENIS_AKSES),
            Filter("akses_disabilitas", "Akses disabilitas", "bool", "akses_disabilitas"),
            Filter("parkir_tersedia", "Parkir", "bool", "parkir_tersedia"),
            Filter("toilet_tersedia", "Toilet", "bool", "toilet_tersedia"),
        ),
        sort=(("nama", 1),),
        editable={"status_operasional": STATUS_OPERASIONAL, "kondisi_fisik": KONDISI_FISIK},
    ),
    "event": TypeSpec(
        name="event",
        label="Event",
        collection="event",
        columns=(
            Column("nama", "Nama"),
            Column("nama_olahraga", "Olahraga"),
            Column("jenis_event", "Jenis"),
            Column("tingkat_event", "Tingkat"),
            Column("tanggal_mulai", "Mulai"),
            Column("tanggal_selesai", "Selesai"),
            Column("status_event", "Status"),
            Column("nama_fasilitas", "Lokasi"),
        ),
        filters=(
            Filter("olahraga_id", "Olahraga", "ref", "olahraga_id", ref="olahraga"),
            Filter("jenis_event", "Jenis event", "enum", "jenis_event", JENIS_EVENT),
            Filter("tingkat_event", "Tingkat", "enum", "tingkat_event", TINGKAT),
            Filter("status_event", "Status", "enum", "status_event", STATUS_EVENT),
            Filter("mulai_dari", "Mulai dari", "date_from", "tanggal_mulai"),
            Filter("mulai_sampai", "Mulai sampai", "date_to", "tanggal_mulai"),
        ),
        sort=(("tanggal_mulai", -1), ("nama", 1)),
        editable={"status_event": STATUS_EVENT, "jumlah_peserta": "nonneg_int"},
    ),
    "atlet": TypeSpec(
        name="atlet",
        label="Atlet",
        collection="atlet",
        columns=(
            Column("nama", "Nama"),
            Column("jenis_kelamin", "Jenis kelamin"),
            Column("olahraga", "Olahraga"),
            Column("nama_organisasi", "Organisasi"),
            Column("nama_kecamatan", "Kecamatan"),
            Column("status_binaan", "Status binaan"),
        ),
        filters=(
            Filter("olahraga_id", "Olahraga", "ref", "atlet_id", ref="olahraga",
                   via=("atlet_olahraga", "olahraga_id", "atlet_id")),
            Filter("kecamatan_id", "Kecamatan domisili", "ref", "kecamatan_domisili_id", ref="kecamatan"),
            Filter("organisasi_id", "Organisasi", "ref", "organisasi_id", ref="organisasi"),
            Filter("jenis_kelamin", "Jenis kelamin", "enum", "jenis_kelamin", JENIS_KELAMIN),
            Filter("status_binaan", "Status binaan", "enum", "status_binaan", STATUS_BINAAN),
            Filter("aktif", "Aktif", "bool", "aktif"),
        ),
        sort=(("nama", 1),),
    ),
    "organisasi": TypeSpec(
        name="organisasi",
        label="Organisasi",
        collection="organisasi",
        columns=(
            Column("nama", "Nama"),
            Column("jenis_organisasi", "Jenis"),
            Column("olahraga", "Olahraga"),
            Column("nama_kecamatan", "Kecamatan"),
            Column("nama_kelurahan", "Kelurahan"),
            Column("status_aktif", "Aktif"),
        ),
        filters=(
            Filter("kecamatan_id", "Kecamatan", "ref", "kelurahan_id", ref="kecamatan",
                   via=("kelurahan", "kecamatan_id", "kelurahan_id")),
            Filter("olahraga_id", "Olahraga", "ref", "organisasi_id", ref="olahraga",
                   via=("organisasi_olahraga", "olahraga_id", "organisasi_id")),
            Filter("jenis_organisasi", "Jenis organisasi", "enum", "jenis_organisasi", JENIS_ORGANISASI),
            Filter("status_aktif", "Aktif", "bool", "status_aktif"),
        ),
        sort=(("nama", 1),),
    ),
}


def _parse(f: Filter, raw: str):
    """Turn one raw query value into a plain scalar (never an operator dict)."""
    if f.kind == "enum":
        if raw not in f.choices:
            raise FilterError(f"{f.param}: must be one of {', '.join(f.choices)}")
        return raw
    if f.kind == "distinct":
        if len(raw) > 100:
            raise FilterError(f"{f.param}: value too long")
        return raw
    if f.kind == "ref":
        if not ID_RE.match(raw):
            raise FilterError(f"{f.param}: invalid id")
        return raw
    if f.kind == "bool":
        if raw not in ("true", "false"):
            raise FilterError(f"{f.param}: must be true or false")
        return raw == "true"
    if f.kind in ("date_from", "date_to"):
        try:
            return date.fromisoformat(raw).isoformat()   # dates are stored as YYYY-MM-DD strings
        except ValueError:
            raise FilterError(f"{f.param}: expected a date YYYY-MM-DD")
    raise FilterError(f"{f.param}: unsupported filter")


def parse_filters(spec: TypeSpec, params: dict[str, str]) -> tuple[list, dict]:
    """Validate query parameters (pure, no database access).

    Returns (criteria, normalized): criteria is a list of (Filter, value) pairs
    that service.py turns into a MongoDB query; normalized is used for cache keys.
    Only declared filters are accepted.
    """
    allowed = {f.param: f for f in spec.filters}
    unknown = sorted(set(params) - allowed.keys())
    if unknown:
        raise FilterError(f"Unknown filter(s): {', '.join(unknown)}")
    criteria: list = []
    normalized: dict = {}
    for param, raw in params.items():
        raw = raw.strip()
        if raw == "":
            continue
        f = allowed[param]
        criteria.append((f, _parse(f, raw)))
        normalized[param] = raw
    return criteria, normalized


def validate_update(spec: TypeSpec, payload: dict) -> dict:
    if not spec.editable:
        raise FilterError(f"{spec.name} is read-only")
    if not payload:
        raise FilterError("Empty update")
    out = {}
    for key, value in payload.items():
        rule = spec.editable.get(key)
        if rule is None:
            raise FilterError(f"{key}: not editable")
        if rule == "nonneg_int":
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise FilterError(f"{key}: must be a non-negative integer")
        elif value not in rule:
            raise FilterError(f"{key}: must be one of {', '.join(rule)}")
        out[key] = value
    return out
