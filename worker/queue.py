"""Queue utilities backed by Redis or fakeredis for local development."""
from __future__ import annotations

import logging
from typing import Optional

import fakeredis
import redis
from redis.exceptions import RedisError
from rq import Queue

from api.config import get_settings

logger = logging.getLogger(__name__)

_FAKE_SERVER = fakeredis.FakeServer()


def get_redis_connection() -> redis.Redis:
    """Return a Redis connection, falling back to in-memory fakeredis.

    When a real Redis instance is unavailable, fakeredis with a module-level
    server is used so that multiple queues in the same process can share state.
    """

    settings = get_settings()
    redis_url = settings.redis_url
    try:
        connection = redis.Redis.from_url(redis_url)
        connection.ping()
        return connection
    except RedisError:
        logger.warning("Redis unavailable at %s, falling back to fakeredis", redis_url)
        return fakeredis.FakeStrictRedis(server=_FAKE_SERVER)


def get_queue(name: Optional[str] = None, connection: Optional[redis.Redis] = None) -> Queue:
    """Create or return an RQ queue bound to the provided connection."""

    settings = get_settings()
    conn = connection or get_redis_connection()
    return Queue(name or settings.queue_name, connection=conn)

