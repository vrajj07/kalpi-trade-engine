"""In-process registry of running executions.

Known limitation: tracking is per process. With several replicas, two could resume the same
execution; a lease column (owner + heartbeat) or SELECT ... FOR UPDATE SKIP LOCKED would make
resumption exclusive.
"""
import asyncio
import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import AsyncSessionLocal

_tasks: dict[uuid.UUID, asyncio.Task[None]] = {}


def is_running(execution_id: uuid.UUID) -> bool:
    return execution_id in _tasks


def start(execution_id: uuid.UUID, job: Callable[[AsyncSession], Awaitable[None]]) -> None:
    """Runs `job` detached from the request, with its own session (the request's closes with it)."""
    async def run() -> None:
        async with AsyncSessionLocal() as session:
            await job(session)

    task = asyncio.create_task(run(), name=f"execution-{execution_id}")
    _tasks[execution_id] = task
    task.add_done_callback(lambda _: _tasks.pop(execution_id, None))


async def shutdown() -> None:
    """Cancels running executions on app shutdown. Safe by design: a cancelled run stays RUNNING,
    its in-flight order is already saved as SUBMITTING, and a resume looks it up by tag first."""
    tasks = list(_tasks.values())
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
