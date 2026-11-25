"""MongoDB aggregations that build the finished list pages and detail records.

One aggregation per cache miss (lists also run countDocuments for the total).
Each pipeline is written out in full so it can be read on its own; they match
AGGREGATION_PLAN.md one to one. Fields starting with `_` hold join results and
are removed before the result leaves MongoDB.

In list pipelines the joins come after $limit, so they only run for the rows
of the page, and they are plain localField/foreignField lookups: a $lookup
with an inner `pipeline` runs once per row (an N+1 inside MongoDB), so lists
return sport names only. Details, which are one record, keep the full objects.
"""


# ---- lists: q = validated filter, skip / limit = paging ---------------------

def fasilitas_list(q: dict, skip: int, limit: int) -> list:
    return [
        {"$match": q},
        {"$sort": {"nama": 1, "fasilitas_id": 1}},
        {"$skip": skip},
        {"$limit": limit},
        {"$lookup": {"from": "kelurahan", "localField": "kelurahan_id",
                     "foreignField": "kelurahan_id", "as": "_kel"}},
        {"$lookup": {"from": "kecamatan", "localField": "_kel.kecamatan_id",
                     "foreignField": "kecamatan_id", "as": "_kec"}},
        # sports: the links of this row, then those sports' names (two plain lookups,
        # no inner pipeline, so MongoDB joins them in one pass instead of once per row)
        {"$lookup": {"from": "fasilitas_olahraga", "localField": "fasilitas_id",
                     "foreignField": "fasilitas_id", "as": "_lnk"}},
        {"$lookup": {"from": "olahraga", "localField": "_lnk.olahraga_id",
                     "foreignField": "olahraga_id", "as": "_o"}},
        {"$project": {
            "_id": 0, "id": "$fasilitas_id", "nama": "$nama", "kategori": "$kategori",
            "olahraga": {"$sortArray": {"input": "$_o.nama", "sortBy": 1}},
            "nama_kecamatan": {"$first": "$_kec.nama"}, "nama_kelurahan": {"$first": "$_kel.nama"},
            "status_operasional": "$status_operasional", "kondisi_fisik": "$kondisi_fisik", "jenis_akses": "$jenis_akses"}},
    ]


def atlet_list(q: dict, skip: int, limit: int) -> list:
    return [
        {"$match": q},
        {"$sort": {"nama": 1, "atlet_id": 1}},
        {"$skip": skip},
        {"$limit": limit},
        {"$lookup": {"from": "organisasi", "localField": "organisasi_id",
                     "foreignField": "organisasi_id", "as": "_org"}},
        {"$lookup": {"from": "kecamatan", "localField": "kecamatan_domisili_id",
                     "foreignField": "kecamatan_id", "as": "_kec"}},
        # sports: the links of this row, then those sports' names (two plain lookups,
        # no inner pipeline, so MongoDB joins them in one pass instead of once per row)
        {"$lookup": {"from": "atlet_olahraga", "localField": "atlet_id",
                     "foreignField": "atlet_id", "as": "_lnk"}},
        {"$lookup": {"from": "olahraga", "localField": "_lnk.olahraga_id",
                     "foreignField": "olahraga_id", "as": "_o"}},
        {"$project": {
            "_id": 0, "id": "$atlet_id", "nama": "$nama", "jenis_kelamin": "$jenis_kelamin",
            "olahraga": {"$sortArray": {"input": "$_o.nama", "sortBy": 1}},
            "nama_organisasi": {"$first": "$_org.nama"}, "nama_kecamatan": {"$first": "$_kec.nama"},
            "status_binaan": "$status_binaan"}},
    ]


def event_list(q: dict, skip: int, limit: int) -> list:
    return [
        {"$match": q},
        {"$sort": {"tanggal_mulai": -1, "nama": 1, "event_id": 1}},
        {"$skip": skip},
        {"$limit": limit},
        {"$lookup": {"from": "olahraga", "localField": "olahraga_id",
                     "foreignField": "olahraga_id", "as": "_o"}},
        {"$lookup": {"from": "fasilitas", "localField": "fasilitas_id",
                     "foreignField": "fasilitas_id", "as": "_fas"}},
        {"$project": {
            "_id": 0, "id": "$event_id", "nama": "$nama", "nama_olahraga": {"$first": "$_o.nama"},
            "jenis_event": "$jenis_event", "tingkat_event": "$tingkat_event", "tanggal_mulai": "$tanggal_mulai", "tanggal_selesai": "$tanggal_selesai",
            "status_event": "$status_event", "nama_fasilitas": {"$ifNull": [{"$first": "$_fas.nama"}, None]}}},
    ]


def organisasi_list(q: dict, skip: int, limit: int) -> list:
    return [
        {"$match": q},
        {"$sort": {"nama": 1, "organisasi_id": 1}},
        {"$skip": skip},
        {"$limit": limit},
        {"$lookup": {"from": "kelurahan", "localField": "kelurahan_id",
                     "foreignField": "kelurahan_id", "as": "_kel"}},
        {"$lookup": {"from": "kecamatan", "localField": "_kel.kecamatan_id",
                     "foreignField": "kecamatan_id", "as": "_kec"}},
        # sports: the links of this row, then those sports' names (two plain lookups,
        # no inner pipeline, so MongoDB joins them in one pass instead of once per row)
        {"$lookup": {"from": "organisasi_olahraga", "localField": "organisasi_id",
                     "foreignField": "organisasi_id", "as": "_lnk"}},
        {"$lookup": {"from": "olahraga", "localField": "_lnk.olahraga_id",
                     "foreignField": "olahraga_id", "as": "_o"}},
        {"$project": {
            "_id": 0, "id": "$organisasi_id", "nama": "$nama", "jenis_organisasi": "$jenis_organisasi",
            "olahraga": {"$sortArray": {"input": "$_o.nama", "sortBy": 1}},
            "nama_kecamatan": {"$first": "$_kec.nama"}, "nama_kelurahan": {"$first": "$_kel.nama"},
            "status_aktif": "$status_aktif"}},
    ]


# ---- details: every stored field except _id, plus names and child lists -----

def fasilitas_detail(item_id: str) -> list:
    return [
        {"$match": {"fasilitas_id": item_id}},
        {"$lookup": {"from": "kelurahan", "localField": "kelurahan_id",
                     "foreignField": "kelurahan_id", "as": "_kel"}},
        {"$lookup": {"from": "kecamatan", "localField": "_kel.kecamatan_id",
                     "foreignField": "kecamatan_id", "as": "_kec"}},
        {"$set": {
            "kecamatan_id": {"$first": "$_kec.kecamatan_id"},
            "nama_kelurahan": {"$first": "$_kel.nama"},
            "nama_kecamatan": {"$first": "$_kec.nama"}}},
        {"$lookup": {"from": "fasilitas_olahraga", "localField": "fasilitas_id",
                     "foreignField": "fasilitas_id", "as": "olahraga", "pipeline": [
                         {"$lookup": {"from": "olahraga", "localField": "olahraga_id",
                                      "foreignField": "olahraga_id", "as": "_o"}},
                         {"$project": {"_id": 0, "olahraga_id": "$olahraga_id", "nama": {"$first": "$_o.nama"},
                                       "jumlah_lapangan": "$jumlah_lapangan"}},
                         {"$sort": {"nama": 1}}]}},
        {"$lookup": {"from": "jadwal_operasional_fasilitas", "localField": "fasilitas_id",
                     "foreignField": "fasilitas_id", "as": "jadwal", "pipeline": [
                         {"$sort": {"hari": 1, "jam_buka": 1}},
                         {"$project": {"_id": 0, "hari": "$hari", "jam_buka": "$jam_buka", "jam_tutup": "$jam_tutup"}}]}},
        {"$unset": ["_id", "_kel", "_kec"]},
    ]


def atlet_detail(item_id: str) -> list:
    return [
        {"$match": {"atlet_id": item_id}},
        {"$lookup": {"from": "kecamatan", "localField": "kecamatan_domisili_id",
                     "foreignField": "kecamatan_id", "as": "_kec"}},
        {"$lookup": {"from": "organisasi", "localField": "organisasi_id",
                     "foreignField": "organisasi_id", "as": "_org"}},
        {"$set": {
            "nama_kecamatan": {"$first": "$_kec.nama"},
            "nama_organisasi": {"$first": "$_org.nama"}}},
        {"$lookup": {"from": "atlet_olahraga", "localField": "atlet_id",
                     "foreignField": "atlet_id", "as": "olahraga", "pipeline": [
                         {"$lookup": {"from": "olahraga", "localField": "olahraga_id",
                                      "foreignField": "olahraga_id", "as": "_o"}},
                         {"$project": {"_id": 0, "olahraga_id": "$olahraga_id", "nama": {"$first": "$_o.nama"}}},
                         {"$sort": {"nama": 1}}]}},
        {"$lookup": {"from": "prestasi", "localField": "atlet_id",
                     "foreignField": "atlet_id", "as": "prestasi", "pipeline": [
                         {"$sort": {"tanggal_perolehan": -1}},
                         {"$lookup": {"from": "event", "localField": "event_id",
                                      "foreignField": "event_id", "as": "_e"}},
                         {"$lookup": {"from": "olahraga", "localField": "_e.olahraga_id",
                                      "foreignField": "olahraga_id", "as": "_o"}},
                         {"$project": {"_id": 0,
                                       "nama_event": {"$first": "$_e.nama"},
                                       "nama_olahraga": {"$first": "$_o.nama"},
                                       "nomor_pertandingan": "$nomor_pertandingan", "peringkat": "$peringkat", "medali": "$medali",
                                       "tanggal_perolehan": "$tanggal_perolehan"}}]}},
        {"$unset": ["_id", "_kec", "_org"]},
    ]


def event_detail(item_id: str) -> list:
    return [
        {"$match": {"event_id": item_id}},
        {"$lookup": {"from": "olahraga", "localField": "olahraga_id",
                     "foreignField": "olahraga_id", "as": "_o"}},
        {"$lookup": {"from": "organisasi", "localField": "organisasi_id",
                     "foreignField": "organisasi_id", "as": "_org"}},
        {"$lookup": {"from": "fasilitas", "localField": "fasilitas_id",
                     "foreignField": "fasilitas_id", "as": "_fas"}},
        {"$set": {
            "nama_olahraga": {"$first": "$_o.nama"},
            "nama_penyelenggara": {"$first": "$_org.nama"},
            "nama_fasilitas": {"$ifNull": [{"$first": "$_fas.nama"}, None]}}},
        {"$lookup": {"from": "prestasi", "localField": "event_id",
                     "foreignField": "event_id", "as": "prestasi", "pipeline": [
                         {"$sort": {"peringkat": 1}},
                         {"$lookup": {"from": "atlet", "localField": "atlet_id",
                                      "foreignField": "atlet_id", "as": "_a"}},
                         {"$project": {"_id": 0, "nama_atlet": {"$ifNull": [{"$first": "$_a.nama"}, None]},
                                       "nomor_pertandingan": "$nomor_pertandingan", "peringkat": "$peringkat", "medali": "$medali",
                                       "tanggal_perolehan": "$tanggal_perolehan"}}]}},
        {"$lookup": {"from": "event_atlet", "localField": "event_id",
                     "foreignField": "event_id", "as": "_ea", "pipeline": [{"$count": "n"}]}},
        {"$set": {"jumlah_atlet_terdaftar": {"$ifNull": [{"$first": "$_ea.n"}, 0]}}},
        {"$unset": ["_id", "_o", "_org", "_fas", "_ea"]},
    ]


def organisasi_detail(item_id: str) -> list:
    return [
        {"$match": {"organisasi_id": item_id}},
        {"$lookup": {"from": "kelurahan", "localField": "kelurahan_id",
                     "foreignField": "kelurahan_id", "as": "_kel"}},
        {"$lookup": {"from": "kecamatan", "localField": "_kel.kecamatan_id",
                     "foreignField": "kecamatan_id", "as": "_kec"}},
        {"$set": {
            "kecamatan_id": {"$first": "$_kec.kecamatan_id"},
            "nama_kelurahan": {"$first": "$_kel.nama"},
            "nama_kecamatan": {"$first": "$_kec.nama"}}},
        {"$lookup": {"from": "organisasi_olahraga", "localField": "organisasi_id",
                     "foreignField": "organisasi_id", "as": "olahraga", "pipeline": [
                         {"$lookup": {"from": "olahraga", "localField": "olahraga_id",
                                      "foreignField": "olahraga_id", "as": "_o"}},
                         {"$project": {"_id": 0, "olahraga_id": "$olahraga_id", "nama": {"$first": "$_o.nama"}}},
                         {"$sort": {"nama": 1}}]}},
        {"$lookup": {"from": "atlet", "localField": "organisasi_id",
                     "foreignField": "organisasi_id", "as": "_at", "pipeline": [{"$count": "n"}]}},
        {"$set": {"jumlah_atlet": {"$ifNull": [{"$first": "$_at.n"}, 0]}}},
        {"$lookup": {"from": "event", "localField": "organisasi_id",
                     "foreignField": "organisasi_id", "as": "event", "pipeline": [
                         {"$sort": {"tanggal_mulai": -1, "nama": 1}},
                         {"$lookup": {"from": "olahraga", "localField": "olahraga_id",
                                      "foreignField": "olahraga_id", "as": "_o"}},
                         {"$project": {"_id": 0, "nama": "$nama", "tanggal_mulai": "$tanggal_mulai", "status_event": "$status_event",
                                       "nama_olahraga": {"$first": "$_o.nama"}}}]}},
        {"$unset": ["_id", "_kel", "_kec", "_at"]},
    ]


LIST = {"fasilitas": fasilitas_list, "atlet": atlet_list, "event": event_list,
        "organisasi": organisasi_list}
DETAIL = {"fasilitas": fasilitas_detail, "atlet": atlet_detail, "event": event_detail,
          "organisasi": organisasi_detail}
