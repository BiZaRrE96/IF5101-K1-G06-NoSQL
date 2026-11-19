# Dispora Web (MongoDB + Redis)

A public website for browsing Kota Bandung sport **facilities, events and athletes** by type, with filters. It continues `../SQL Bab 3` (relational model) and `../NoSQL KV` (key-value design). The design is in [ARCHITECTURE.md](ARCHITECTURE.md).

```
frontend/   nginx: static site (public/) + /api proxy
backend/    FastAPI API + maintenance worker (same image)
mongo/      MongoDB 8.0 image; init/ runs on an empty volume; seed/ holds the team export (imported by init/10-import.sh)
redis/      Redis 7.4 cache config (no persistence)
compose.yaml
```

## Run

```powershell
Copy-Item .env.example .env   # then set both Mongo passwords (letters/digits)
docker compose up -d --build --wait
```

The first `up` takes longer than later ones, because MongoDB imports the team export (about 90,000 documents in the main collections, mostly facility schedules) and builds the indexes. Later starts reuse the volume and skip the import.

Open http://localhost:8080. The API is at http://localhost:8080/api/types.

MongoDB is reachable for mongosh or Compass at `mongodb://root:<MONGO_ROOT_PASSWORD>@localhost:57017`.

## Maintenance worker

```powershell
docker compose run --rm worker ping
docker compose run --rm worker ensure-indexes
docker compose run --rm worker warm          # only with CACHE_ENABLED=true
docker compose run --rm worker bench [runs]  # MISS vs HIT timing table (Markdown), for the report
docker compose run --rm worker flush-cache   # deletes this app's keys only
```

## Status

- The team's MongoDB export is in `mongo/seed/` and loads automatically on the first `up`. See [mongo/init/README.md](mongo/init/README.md). Init scripts run only on an empty volume, and `docker compose down -v` resets it (this deletes all data and the next start re-imports).
- `fasilitas.kategori` is normalized on import: `GOR` and `Gedung Olahraga` become `gedung_olahraga` (ARCHITECTURE.md §5).
- The Redis cache is on by default (`CACHE_ENABLED=true`). The site still works with Redis down.
- Writes (`PATCH`) are off unless `ADMIN_TOKEN` is set.

## Verified (19 Nov 2026, full team export, disposable stack)

- Import: all 18 collections match the export counts, the kategori fix changed 3,162 documents, and 34 indexes were created.
- 28 filter combinations across the three types match totals computed directly from the export JSON. Sorting, pagination, joined names, schedules (`jadwal`), achievements (`prestasi`) and `jumlah_atlet_terdaftar` are correct.
- `_id` and athlete personal data never appear in responses. Invalid input returns 400; `page_size` out of range returns FastAPI's 422.
- Cache: MISS then HIT, invalidation after PATCH, and fail-open with Redis stopped.
- The UI works in the browser, with no console errors.

`worker bench 5`, in ms:

| scenario | miss mean | hit mean | speedup |
|---|---:|---:|---:|
| fasilitas list, no filter | 10.8 | 0.6 | 18.9x |
| fasilitas list, kecamatan + aktif | 8.7 | 0.6 | 14.8x |
| fasilitas list, olahraga | 6.6 | 0.5 | 14.5x |
| fasilitas detail | 4.8 | 0.2 | 25.5x |
| atlet list, perempuan + binaan | 15.7 | 0.5 | 33.5x |
| atlet detail | 5.9 | 0.2 | 29.0x |
| event list | 5.0 | 0.6 | 8.8x |
| event detail | 4.3 | 0.2 | 18.6x |

For the report, rerun with more runs (for example `bench 50`) on the machine used for the presentation.
