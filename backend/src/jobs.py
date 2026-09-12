"""In-memory registry for a live analysis run.

One run at a time is the demo reality, so the events a run produces live in
this process and the browser polls for them. No broker, no database: a job is
dropped once it has aged out of the list below.
"""

import asyncio
import time
import uuid
from typing import Any, Awaitable, Callable, Literal

from pydantic import BaseModel, Field

# The pipeline stages the UI draws as a progress rail, in order.
Stage = Literal["search", "rank", "scrape", "vision", "audit", "report"]
Tone = Literal["info", "ok", "warn"]
JobStatus = Literal["running", "done", "error"]

# Enough history for a demo session; older finished jobs are discarded.
MAX_JOBS = 40


class JobEvent(BaseModel):
    seq: int
    at_ms: int
    stage: Stage
    message: str
    detail: str = ""
    tone: Tone = "info"
    data: dict[str, Any] = Field(default_factory=dict)


class Job:
    def __init__(self) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.started = time.monotonic()
        self.status: JobStatus = "running"
        self.error = ""
        self.result: Any = None
        self.events: list[JobEvent] = []
        self.task: asyncio.Task | None = None

    @property
    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self.started) * 1000)

    def emit(
        self,
        stage: Stage,
        message: str,
        *,
        detail: str = "",
        tone: Tone = "info",
        **data: Any,
    ) -> None:
        self.events.append(
            JobEvent(
                seq=len(self.events),
                at_ms=self.elapsed_ms,
                stage=stage,
                message=message,
                detail=detail,
                tone=tone,
                data=data,
            )
        )

    def since(self, cursor: int) -> list[JobEvent]:
        return self.events[max(0, cursor) :]


_JOBS: dict[str, Job] = {}


def _prune() -> None:
    finished = [job for job in _JOBS.values() if job.status != "running"]
    for job in sorted(finished, key=lambda j: j.started)[: len(_JOBS) - MAX_JOBS]:
        _JOBS.pop(job.id, None)


def get(job_id: str) -> Job | None:
    return _JOBS.get(job_id)


def start(work: Callable[[Job], Awaitable[Any]]) -> Job:
    """Register a job and run `work` in the background."""
    job = Job()
    _JOBS[job.id] = job
    _prune()

    async def runner() -> None:
        try:
            job.result = await work(job)
            job.status = "done"
        except asyncio.CancelledError:
            job.status = "error"
            job.error = "Run cancelled"
            raise
        except Exception as exc:  # surfaced to the UI, not swallowed
            job.status = "error"
            job.error = f"{type(exc).__name__}: {exc}"[:400]
            job.emit("report", "Run failed", detail=job.error, tone="warn")

    job.task = asyncio.create_task(runner())
    return job
