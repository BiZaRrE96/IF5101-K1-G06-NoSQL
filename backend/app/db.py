"""MongoDB access (durable storage, source of truth)."""
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from bson import Decimal128, ObjectId
from pymongo import MongoClient

from . import config

_client: MongoClient | None = None


def get_db():
    global _client
    if _client is None:
        _client = MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=3000, tz_aware=True)
    return _client[config.MONGO_DB]


def clean(value):
    """Convert BSON values into JSON-safe values (used for responses and cache payloads)."""
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, Decimal128):
        return str(value.to_decimal())
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (ObjectId, UUID)):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value
