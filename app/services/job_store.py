import asyncio
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import uuid4


JobState = Literal["pending", "running", "completed", "failed"]


@dataclass
class SyncJob:
    job_id: str
    status: JobState = "pending"
    total: int = 0
    processed: int = 0
    succeeded: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)
    results: list[dict[str, Any]] = field(default_factory=list)


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, SyncJob] = {}
        self._lock = asyncio.Lock()

    async def create_job(self) -> SyncJob:
        async with self._lock:
            job = SyncJob(job_id=str(uuid4()))
            self._jobs[job.job_id] = job
            return job

    async def get_job(self, job_id: str) -> SyncJob | None:
        async with self._lock:
            return self._jobs.get(job_id)

    async def update_job(self, job_id: str, **kwargs: Any) -> SyncJob | None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            for key, value in kwargs.items():
                setattr(job, key, value)
            return job


job_store = JobStore()