"""In-process generation job queue with SQLite persistence.

Provides a single-worker job runner that processes art generation requests
sequentially (Semaphore(1)) to stay within LXC resource limits and AI
provider quotas.

Job lifecycle:  pending → running → completed | failed
On restart:     running jobs are marked failed (recoverable by re-submit).
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Coroutine, Optional

import aiosqlite

logger = logging.getLogger(__name__)

JOBS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS generation_jobs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'pending',
    source_type TEXT NOT NULL,
    art_type TEXT,
    variant TEXT,
    photo_path TEXT,
    progress TEXT,
    asset_id TEXT,
    error TEXT,
    priority INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    started_at TEXT,
    completed_at TEXT,
    metadata_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON generation_jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON generation_jobs(created_at DESC);
"""


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class GenerationJob:
    __slots__ = (
        "id", "status", "source_type", "art_type", "variant",
        "photo_path", "progress", "asset_id", "error", "priority",
        "created_at", "started_at", "completed_at", "metadata",
    )

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def to_dict(self) -> dict:
        return {
            "job_id": self.id,
            "status": self.status,
            "source_type": self.source_type,
            "art_type": self.art_type,
            "variant": self.variant,
            "progress": self.progress,
            "asset_id": self.asset_id,
            "error": self.error,
            "priority": self.priority,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


# Type alias for the async callable that actually does the generation work.
# Signature: (job: GenerationJob) -> str  (returns asset_id)
GenerationWorkerFn = Callable[[GenerationJob], Coroutine[Any, Any, str]]


class JobQueue:
    """SQLite-backed, single-worker generation job queue."""

    def __init__(self, db: aiosqlite.Connection, worker_fn: GenerationWorkerFn):
        self._db = db
        self._worker_fn = worker_fn
        self._semaphore = asyncio.Semaphore(1)
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._runner_task: Optional[asyncio.Task] = None

    async def init(self) -> None:
        """Create the jobs table and recover stale running jobs."""
        await self._db.executescript(JOBS_TABLE_SQL)
        await self._db.commit()

        # Mark any 'running' jobs as failed (service was restarted mid-job)
        await self._db.execute(
            "UPDATE generation_jobs SET status = ?, error = ? WHERE status = ?",
            (JobStatus.FAILED, "Service restarted during generation", JobStatus.RUNNING),
        )
        await self._db.commit()

        # Re-queue any pending jobs
        async with self._db.execute(
            "SELECT id FROM generation_jobs WHERE status = ? ORDER BY priority DESC, created_at ASC",
            (JobStatus.PENDING,),
        ) as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                self._queue.put_nowait(row["id"])
                logger.info(f"Re-queued pending job: {row['id']}")

    def start(self) -> None:
        """Start the background runner."""
        self._runner_task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Gracefully stop the runner."""
        if self._runner_task:
            self._runner_task.cancel()
            try:
                await self._runner_task
            except asyncio.CancelledError:
                pass

    async def submit(
        self,
        source_type: str,
        art_type: Optional[str] = None,
        variant: Optional[str] = None,
        photo_path: Optional[str] = None,
        priority: int = 0,
        metadata: Optional[dict] = None,
    ) -> GenerationJob:
        """Create a new generation job and enqueue it."""
        job_id = str(uuid.uuid4())
        await self._db.execute(
            """INSERT INTO generation_jobs
               (id, status, source_type, art_type, variant, photo_path, priority, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id, JobStatus.PENDING, source_type, art_type, variant,
                photo_path, priority,
                json.dumps(metadata) if metadata else None,
            ),
        )
        await self._db.commit()

        self._queue.put_nowait(job_id)
        logger.info(f"Job submitted: {job_id} ({source_type}/{art_type})")

        return await self.get(job_id)

    async def get(self, job_id: str) -> Optional[GenerationJob]:
        async with self._db.execute(
            "SELECT * FROM generation_jobs WHERE id = ?", (job_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return self._row_to_job(row)

    async def list_recent(self, limit: int = 20) -> list[GenerationJob]:
        async with self._db.execute(
            "SELECT * FROM generation_jobs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_job(r) for r in rows]

    async def cleanup_old(self, max_age_hours: int = 24) -> int:
        """Delete completed/failed jobs older than max_age_hours."""
        cutoff = (datetime.utcnow() - timedelta(hours=max_age_hours)).strftime("%Y-%m-%d %H:%M:%S")
        cursor = await self._db.execute(
            "DELETE FROM generation_jobs WHERE status IN (?, ?) AND created_at < ?",
            (JobStatus.COMPLETED, JobStatus.FAILED, cutoff),
        )
        await self._db.commit()
        return cursor.rowcount

    async def _update_status(
        self,
        job_id: str,
        status: str,
        *,
        progress: Optional[str] = None,
        asset_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        fields = ["status = ?"]
        values: list[Any] = [status]

        if progress is not None:
            fields.append("progress = ?")
            values.append(progress)
        if asset_id is not None:
            fields.append("asset_id = ?")
            values.append(asset_id)
        if error is not None:
            fields.append("error = ?")
            values.append(error)

        if status == JobStatus.RUNNING:
            fields.append("started_at = datetime('now')")
        elif status in (JobStatus.COMPLETED, JobStatus.FAILED):
            fields.append("completed_at = datetime('now')")

        values.append(job_id)
        await self._db.execute(
            f"UPDATE generation_jobs SET {', '.join(fields)} WHERE id = ?",
            values,
        )
        await self._db.commit()

    async def _run_loop(self) -> None:
        """Background loop that pulls jobs from the queue and processes them."""
        logger.info("Job queue runner started")
        try:
            while True:
                job_id = await self._queue.get()
                async with self._semaphore:
                    await self._process_job(job_id)
        except asyncio.CancelledError:
            logger.info("Job queue runner stopped")
            raise

    async def _process_job(self, job_id: str) -> None:
        job = await self.get(job_id)
        if not job or job.status != JobStatus.PENDING:
            return

        logger.info(f"Processing job: {job_id} ({job.source_type}/{job.art_type})")
        await self._update_status(job_id, JobStatus.RUNNING, progress="Starting generation")

        try:
            # Reload so the worker sees the latest state
            job = await self.get(job_id)
            asset_id = await self._worker_fn(job)
            await self._update_status(
                job_id, JobStatus.COMPLETED,
                progress="Complete", asset_id=asset_id,
            )
            logger.info(f"Job completed: {job_id} → asset {asset_id}")
        except Exception as e:
            logger.error(f"Job failed: {job_id} — {e}", exc_info=True)
            await self._update_status(
                job_id, JobStatus.FAILED,
                progress="Failed", error=str(e),
            )

    @staticmethod
    def _row_to_job(row: aiosqlite.Row) -> GenerationJob:
        return GenerationJob(
            id=row["id"],
            status=row["status"],
            source_type=row["source_type"],
            art_type=row["art_type"],
            variant=row["variant"],
            photo_path=row["photo_path"],
            progress=row["progress"],
            asset_id=row["asset_id"],
            error=row["error"],
            priority=row["priority"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            metadata=json.loads(row["metadata_json"]) if row["metadata_json"] else None,
        )
