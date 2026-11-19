#!/bin/bash
# Runs once on an empty volume (docker-entrypoint-initdb.d, after 00-*).
# 1. Imports every /opt/dispora/seed/*.json (mongoexport --jsonArray) into a collection named after the file.
# 2. Applies the approved kategori fix, creates indexes, prints document counts.
set -euo pipefail

DB="${MONGO_INITDB_DATABASE:-dispora}"
SEED_DIR=/opt/dispora/seed
AUTH=(
  --host 127.0.0.1
  --username "$MONGO_INITDB_ROOT_USERNAME"
  --password "$MONGO_INITDB_ROOT_PASSWORD"
  --authenticationDatabase admin
)

shopt -s nullglob
files=("$SEED_DIR"/*.json)
if [ ${#files[@]} -eq 0 ]; then
  echo "no seed files found in $SEED_DIR" >&2
  exit 1
fi

for file in "${files[@]}"; do
  coll="$(basename "$file" .json)"
  echo "importing collection: $coll"
  mongoimport "${AUTH[@]}" --db "$DB" --collection "$coll" --jsonArray --file "$file"
done

# One mongosh session for the data fix, the indexes and the final counts.
# The script is passed on stdin; DB_NAME is read via process.env.
DB_NAME="$DB" mongosh --quiet "${AUTH[@]}" <<'JS'
const d = db.getSiblingDB(process.env.DB_NAME);

// a. Data fix (team decision): unify kategori spellings.
const fix = d.fasilitas.updateMany(
  { kategori: { $in: ["GOR", "Gedung Olahraga"] } },
  { $set: { kategori: "gedung_olahraga" } }
);
print(`kategori fix: modified ${fix.modifiedCount} (expected 3162)`);

// b. Indexes: [collection, keys, options]
const indexes = [
  ["fasilitas", { fasilitas_id: 1 }, { unique: true }],
  ["atlet", { atlet_id: 1 }, { unique: true }],
  ["event", { event_id: 1 }, { unique: true }],
  ["prestasi", { prestasi_id: 1 }, { unique: true }],
  ["kecamatan", { kecamatan_id: 1 }, { unique: true }],
  ["kelurahan", { kelurahan_id: 1 }, { unique: true }],
  ["olahraga", { olahraga_id: 1 }, { unique: true }],
  ["organisasi", { organisasi_id: 1 }, { unique: true }],
  ["jadwal_operasional_fasilitas", { jadwal_id: 1 }, { unique: true }],

  ["jadwal_operasional_fasilitas", { fasilitas_id: 1, hari: 1 }, {}],
  ["fasilitas_olahraga", { olahraga_id: 1 }, {}],
  ["fasilitas_olahraga", { fasilitas_id: 1 }, {}],
  ["atlet_olahraga", { olahraga_id: 1 }, {}],
  ["atlet_olahraga", { atlet_id: 1 }, {}],
  ["kelurahan", { kecamatan_id: 1 }, {}],
  ["prestasi", { atlet_id: 1 }, {}],
  ["prestasi", { event_id: 1 }, {}],
  ["event_atlet", { event_id: 1 }, {}],

  ["fasilitas", { nama: 1, fasilitas_id: 1 }, {}],
  ["fasilitas", { kelurahan_id: 1 }, {}],
  ["fasilitas", { kategori: 1 }, {}],
  ["fasilitas", { status_operasional: 1 }, {}],
  ["fasilitas", { kondisi_fisik: 1 }, {}],
  ["fasilitas", { jenis_akses: 1 }, {}],

  ["atlet", { nama: 1, atlet_id: 1 }, {}],
  ["atlet", { kecamatan_domisili_id: 1 }, {}],
  ["atlet", { organisasi_id: 1 }, {}],
  ["atlet", { jenis_kelamin: 1 }, {}],
  ["atlet", { status_binaan: 1 }, {}],

  ["event", { tanggal_mulai: -1, nama: 1, event_id: 1 }, {}],
  ["event", { olahraga_id: 1 }, {}],

  ["kecamatan", { nama: 1 }, {}],
  ["olahraga", { nama: 1 }, {}],
  ["organisasi", { nama: 1 }, {}],
];

for (const [coll, keys, opts] of indexes) {
  d[coll].createIndex(keys, opts);
}
print(`indexes created: ${indexes.length}`);

// Final line: document counts.
print(
  `counts: fasilitas=${d.fasilitas.countDocuments({})} ` +
  `atlet=${d.atlet.countDocuments({})} ` +
  `jadwal_operasional_fasilitas=${d.jadwal_operasional_fasilitas.countDocuments({})}`
);
JS
