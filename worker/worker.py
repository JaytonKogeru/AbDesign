"""Entry point for running the background worker."""
from __future__ import annotations

import logging

from rq import Connection, Worker

from worker.queue import get_queue, get_redis_connection
from worker import tasks  # noqa: F401  # ensure task functions are discoverable
from api.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()
    connection = get_redis_connection()
    queue = get_queue(name=settings.queue_name, connection=connection)
    with Connection(connection):
        worker = Worker([queue])
        logger.info("Starting worker for queues: %s", queue.name)
        worker.work()


if __name__ == "__main__":
    main()

