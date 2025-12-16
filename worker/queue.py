"""Queue utilities backed by Redis or fakeredis for local development."""
from __future__ import annotations

import os
import logging
from typing import Optional

import fakeredis
import redis
from redis.exceptions import RedisError
from rq import Queue

logger = logging.getLogger(__name__)

_FAKE_SERVER = fakeredis.FakeServer()


def get_redis_connection() -> redis.Redis:
    """Return a Redis connection, falling back to in-memory fakeredis.

    When a real Redis instance is unavailable, fakeredis with a module-level
    server is used so that multiple queues in the same process can share state.
    """

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        connection = redis.Redis.from_url(redis_url)
        connection.ping()
        return connection
    except RedisError:
        logger.warning("Redis unavailable at %s, falling back to fakeredis", redis_url)
        return fakeredis.FakeStrictRedis(server=_FAKE_SERVER)


def get_queue(name: str = "default", connection: Optional[redis.Redis] = None) -> Queue:
    """Create or return an RQ queue bound to the provided connection."""

    conn = connection or get_redis_connection()
    return Queue(name, connection=conn)

