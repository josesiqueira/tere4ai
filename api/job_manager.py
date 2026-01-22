"""
Job Manager for Async Processing

Manages background jobs for the TERE4AI analysis pipeline.
Tracks progress through RE phases and stores results.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from api.models import JobStatus, ProcessingPhase

logger = logging.getLogger(__name__)


@dataclass
class Job:
    """Represents an analysis job"""

    job_id: str
    status: JobStatus = JobStatus.PENDING
    phase: ProcessingPhase = ProcessingPhase.QUEUED
    progress: float = 0.0
    message: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

    # Input
    description: str = ""
    context: Optional[str] = None

    # Result
    result: Optional[dict[str, Any]] = None

    def update(
        self,
        status: Optional[JobStatus] = None,
        phase: Optional[ProcessingPhase] = None,
        progress: Optional[float] = None,
        message: Optional[str] = None,
        error: Optional[str] = None,
    ):
        """Update job state"""
        if status is not None:
            self.status = status
        if phase is not None:
            self.phase = phase
        if progress is not None:
            self.progress = progress
        if message is not None:
            self.message = message
        if error is not None:
            self.error = error
        self.updated_at = datetime.now()

        if status == JobStatus.COMPLETED or status == JobStatus.FAILED:
            self.completed_at = datetime.now()


class JobManager:
    """
    Manages async analysis jobs.

    Stores jobs in memory (for MVP - would use Redis/DB in production).
    Provides progress tracking for the frontend.
    """

    # Progress percentages for each phase
    PHASE_PROGRESS = {
        ProcessingPhase.QUEUED: 0.0,
        ProcessingPhase.ELICITATION: 15.0,
        ProcessingPhase.ANALYSIS: 35.0,
        ProcessingPhase.SPECIFICATION: 60.0,
        ProcessingPhase.VALIDATION: 85.0,
        ProcessingPhase.FINALIZING: 95.0,
        ProcessingPhase.COMPLETE: 100.0,
    }

    PHASE_MESSAGES = {
        ProcessingPhase.QUEUED: "Job queued for processing...",
        ProcessingPhase.ELICITATION: "Extracting system characteristics...",
        ProcessingPhase.ANALYSIS: "Classifying risk level...",
        ProcessingPhase.SPECIFICATION: "Generating requirements...",
        ProcessingPhase.VALIDATION: "Validating completeness...",
        ProcessingPhase.FINALIZING: "Finalizing report...",
        ProcessingPhase.COMPLETE: "Analysis complete",
    }

    def __init__(self, max_jobs: int = 100):
        self.jobs: dict[str, Job] = {}
        self.max_jobs = max_jobs
        self._lock = asyncio.Lock()

    async def create_job(self, description: str, context: Optional[str] = None) -> str:
        """Create a new analysis job and return its ID"""
        async with self._lock:
            # Clean up old completed jobs if we have too many
            if len(self.jobs) >= self.max_jobs:
                self._cleanup_old_jobs()

            job_id = str(uuid4())
            job = Job(
                job_id=job_id,
                description=description,
                context=context,
                status=JobStatus.PENDING,
                phase=ProcessingPhase.QUEUED,
                progress=0.0,
                message=self.PHASE_MESSAGES[ProcessingPhase.QUEUED],
            )
            self.jobs[job_id] = job

            logger.info(f"Created job {job_id}")
            return job_id

    async def get_job(self, job_id: str) -> Optional[Job]:
        """Get a job by ID (thread-safe read)"""
        async with self._lock:
            return self.jobs.get(job_id)

    async def update_phase(self, job_id: str, phase: ProcessingPhase):
        """Update job to a new phase with corresponding progress"""
        async with self._lock:
            job = self.jobs.get(job_id)
            if job:
                progress = self.PHASE_PROGRESS.get(phase, job.progress)
                message = self.PHASE_MESSAGES.get(phase, "")
                status = JobStatus.RUNNING if phase != ProcessingPhase.COMPLETE else JobStatus.COMPLETED
                job.update(
                    status=status,
                    phase=phase,
                    progress=progress,
                    message=message,
                )
                logger.debug(f"Job {job_id}: phase={phase.value}, progress={progress}%")
            else:
                logger.warning(f"Job {job_id} not found for phase update")

    async def set_result(self, job_id: str, result: dict[str, Any]):
        """Set the job result and mark as completed"""
        async with self._lock:
            job = self.jobs.get(job_id)
            if job:
                job.result = result
                job.update(
                    status=JobStatus.COMPLETED,
                    phase=ProcessingPhase.COMPLETE,
                    progress=100.0,
                    message="Analysis complete",
                )
                logger.info(f"Job {job_id} completed")
            else:
                logger.warning(f"Job {job_id} not found for result update")

    async def set_error(self, job_id: str, error: str):
        """Mark job as failed with error message"""
        async with self._lock:
            job = self.jobs.get(job_id)
            if job:
                job.update(
                    status=JobStatus.FAILED,
                    error=error,
                    message=f"Error: {error[:100]}",
                )
                logger.error(f"Job {job_id} failed: {error}")
            else:
                logger.warning(f"Job {job_id} not found for error update")

    def _cleanup_old_jobs(self):
        """Remove oldest completed/failed jobs"""
        completed_jobs = [
            (job_id, job)
            for job_id, job in self.jobs.items()
            if job.status in (JobStatus.COMPLETED, JobStatus.FAILED)
        ]
        # Sort by completion time
        completed_jobs.sort(key=lambda x: x[1].completed_at or x[1].created_at)

        # Remove oldest half
        for job_id, _ in completed_jobs[: len(completed_jobs) // 2]:
            del self.jobs[job_id]
            logger.debug(f"Cleaned up old job {job_id}")


# Global job manager instance
job_manager = JobManager()
