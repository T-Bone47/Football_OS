"""Background Job System & Governed Retry Engine for Phase 16.

Governs asynchronous long-running workloads:
- ingestion
- feature_refresh
- model_evaluation
- research_experiments
- bulk_outcome_evaluation
- report_generation
- replay
- large_scenario_analysis

Retry Policy:
- Distinguishes TRANSIENT, PERMANENT, AUTH, RATE_LIMIT, DATA_QUALITY.
- Bounded retries (max 3); never infinitely retry.
- Never retry permanent validation failures.
"""

from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, Field

from app.phase16 import JobStatus
from app.dev_fixtures import dev_seed_enabled


class ProductionJob(BaseModel):
    job_id: str
    job_type: str
    status: JobStatus = JobStatus.QUEUED
    progress_percent: float = 0.0
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: str | None = None
    completed_at: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    result_reference: str | None = None
    retry_count: int = 0
    max_retries: int = 3
    last_error_category: str | None = None  # TRANSIENT, PERMANENT, AUTH, RATE_LIMIT, DATA_QUALITY
    error_message: str | None = None


class BackgroundJobManager:
    """Manages asynchronous worker job lifecycle and bounded retries."""

    def __init__(self) -> None:
        self._jobs: dict[str, ProductionJob] = {}

    def enqueue_job(
        self,
        job_id: str,
        job_type: str,
        parameters: dict[str, Any] | None = None,
        max_retries: int = 3,
    ) -> ProductionJob:
        job = ProductionJob(
            job_id=job_id,
            job_type=job_type,
            parameters=parameters or {},
            max_retries=max_retries,
        )
        self._jobs[job_id] = job
        return job

    def start_job(self, job_id: str) -> ProductionJob:
        job = self.get_job(job_id)
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc).isoformat()
        return job

    def complete_job(self, job_id: str, result_reference: str) -> ProductionJob:
        job = self.get_job(job_id)
        job.status = JobStatus.SUCCESS
        job.progress_percent = 100.0
        job.completed_at = datetime.now(timezone.utc).isoformat()
        job.result_reference = result_reference
        return job

    def fail_job(
        self,
        job_id: str,
        error_message: str,
        error_category: str,  # TRANSIENT, PERMANENT, AUTH, RATE_LIMIT, DATA_QUALITY
    ) -> ProductionJob:
        job = self.get_job(job_id)
        job.error_message = error_message
        job.last_error_category = error_category

        # Governed retry policy
        is_retryable = error_category in ("TRANSIENT", "RATE_LIMIT")
        if is_retryable and (job.retry_count + 1) < job.max_retries:
            job.retry_count += 1
            job.status = JobStatus.RETRYING
        else:
            if is_retryable:
                job.retry_count += 1
            job.status = JobStatus.FAILED
            job.completed_at = datetime.now(timezone.utc).isoformat()

        return job

    def get_job(self, job_id: str) -> ProductionJob:
        if job_id not in self._jobs:
            raise KeyError(f"Job '{job_id}' not found.")
        return self._jobs[job_id]

    def list_jobs(self, status: JobStatus | None = None) -> list[ProductionJob]:
        jobs = list(self._jobs.values())
        if status:
            jobs = [j for j in jobs if j.status == status]
        return jobs


_GLOBAL_JOB_MANAGER: BackgroundJobManager | None = None


def get_job_manager() -> BackgroundJobManager:
    global _GLOBAL_JOB_MANAGER
    if _GLOBAL_JOB_MANAGER is None:
        _GLOBAL_JOB_MANAGER = BackgroundJobManager()
        if dev_seed_enabled():  # demo fixtures only (DEV_SEED)
            # Seed realistic jobs
            j = _GLOBAL_JOB_MANAGER.enqueue_job(
                job_id="job_sync_epl_matchday_28",
                job_type="INGESTION_SYNC",
                parameters={"competition": "EPL", "season": "2023/24"},
            )
            _GLOBAL_JOB_MANAGER.start_job(j.job_id)
            _GLOBAL_JOB_MANAGER.complete_job(j.job_id, result_reference="snapshot_epl_md28_digest")
    return _GLOBAL_JOB_MANAGER
