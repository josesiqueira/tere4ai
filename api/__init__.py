"""
TERE4AI Web API Package

FastAPI-based web interface for TERE4AI.

Usage:
    # Start the server
    uvicorn api.main:app --reload

    # Or via entry point
    tere4ai-api
"""

from api.main import app
from api.job_manager import JobManager, job_manager
from api.models import (
    AnalyzeRequest,
    AnalyzeResponse,
    ExampleSystem,
    ExamplesResponse,
    ExportFormat,
    JobStatus,
    JobStatusResponse,
    ProcessingPhase,
    ReportResponse,
)

__all__ = [
    "app",
    "job_manager",
    "JobManager",
    "AnalyzeRequest",
    "AnalyzeResponse",
    "ExampleSystem",
    "ExamplesResponse",
    "ExportFormat",
    "JobStatus",
    "JobStatusResponse",
    "ProcessingPhase",
    "ReportResponse",
]
