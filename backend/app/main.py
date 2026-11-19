"""HTTP API for the Dispora public data site."""
import hmac
import logging
import time

from fastapi import Body, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from . import cache, config, service
from .db import get_db
from .schema import TYPES, FilterError, ID_RE, TypeSpec, parse_filters, validate_update

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(title="Dispora Web API", version="0.1.0")


def _spec(type_name: str) -> TypeSpec:
    spec = TYPES.get(type_name)
    if spec is None:
        raise HTTPException(404, "Unknown data type")
    return spec


def _check_id(item_id: str) -> None:
    if not ID_RE.match(item_id):
        raise HTTPException(400, "Invalid id")


def _finish(response: Response, value, status: str, started: float):
    response.headers["X-Cache"] = status
    response.headers["Server-Timing"] = f"app;dur={(time.perf_counter() - started) * 1000:.1f}"
    return value


@app.exception_handler(PyMongoError)
def mongo_unavailable(request: Request, exc: PyMongoError):
    logging.getLogger("dispora.api").error("MongoDB error: %s", exc)
    return JSONResponse({"detail": "Database unavailable"}, status_code=503)


@app.get("/api/health")
def health(response: Response):
    result = {"mongo": "down", "redis": "disabled"}
    try:
        get_db().command("ping")
        result["mongo"] = "ok"
    except PyMongoError:
        response.status_code = 503
    if config.CACHE_ENABLED:
        result["redis"] = "ok" if cache.ping() else "down"   # degraded, not fatal
    return result


@app.get("/api/types")
def list_types():
    return [
        {
            "name": s.name,
            "label": s.label,
            "columns": [{"field": c.field, "label": c.label} for c in s.columns],
        }
        for s in TYPES.values()
    ]


# Declared before /{item_id} so "filters" is never treated as an id.
@app.get("/api/{type_name}/filters")
def get_filters(type_name: str, response: Response):
    started = time.perf_counter()
    value, status = service.filter_options(_spec(type_name))
    return _finish(response, value, status, started)


@app.get("/api/{type_name}")
def list_items(
    type_name: str,
    request: Request,
    response: Response,
    page: int = Query(1, ge=1, le=10_000),
    page_size: int = Query(config.DEFAULT_PAGE_SIZE, ge=1, le=config.MAX_PAGE_SIZE),
):
    started = time.perf_counter()
    spec = _spec(type_name)
    params = {k: v for k, v in request.query_params.items() if k not in ("page", "page_size")}
    try:
        criteria, normalized = parse_filters(spec, params)
    except FilterError as exc:
        raise HTTPException(400, str(exc))
    value, status = service.list_page(spec, criteria, normalized, page, page_size)
    return _finish(response, value, status, started)


@app.get("/api/{type_name}/{item_id}")
def get_item(type_name: str, item_id: str, response: Response):
    started = time.perf_counter()
    spec = _spec(type_name)
    _check_id(item_id)
    value, status = service.get_detail(spec, item_id)
    if value is None:
        raise HTTPException(404, "Not found")
    return _finish(response, value, status, started)


@app.patch("/api/{type_name}/{item_id}")
def patch_item(
    type_name: str,
    item_id: str,
    payload: dict = Body(...),
    x_admin_token: str = Header(default=""),
):
    if not config.ADMIN_TOKEN or not hmac.compare_digest(x_admin_token, config.ADMIN_TOKEN):
        raise HTTPException(403, "Writes are disabled or the admin token is wrong")
    spec = _spec(type_name)
    _check_id(item_id)
    try:
        changes = validate_update(spec, payload)
    except FilterError as exc:
        raise HTTPException(400, str(exc))
    updated = service.update(spec, item_id, changes)
    if updated is None:
        raise HTTPException(404, "Not found")
    return updated
