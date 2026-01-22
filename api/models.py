"""
API Request/Response Models

Pydantic models for the FastAPI endpoints.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    """Request model for POST /api/analyze"""

    description: str = Field(
        ...,
        min_length=10,
        max_length=10000,
        description="Natural language description of the AI system"
    )
    context: Optional[str] = Field(
        None,
        max_length=5000,
        description="Optional additional context about the system"
    )


class JobStatus(str, Enum):
    """Status of an analysis job"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ProcessingPhase(str, Enum):
    """Current phase in the RE pipeline"""
    QUEUED = "queued"
    ELICITATION = "elicitation"
    ANALYSIS = "analysis"
    SPECIFICATION = "specification"
    VALIDATION = "validation"
    FINALIZING = "finalizing"
    COMPLETE = "complete"


class JobStatusResponse(BaseModel):
    """Response model for GET /api/status/{job_id}"""

    job_id: str
    status: JobStatus
    phase: ProcessingPhase
    progress: float = Field(..., ge=0.0, le=100.0, description="Progress percentage 0-100")
    message: str = ""
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class AnalyzeResponse(BaseModel):
    """Response model for POST /api/analyze"""

    job_id: str
    status: JobStatus
    message: str


class ExampleSystem(BaseModel):
    """Example AI system description"""

    id: str
    name: str
    category: str
    description: str
    expected_risk_level: str


class ExamplesResponse(BaseModel):
    """Response model for GET /api/examples"""

    examples: list[ExampleSystem]


class ExportFormat(str, Enum):
    """Supported export formats"""
    JSON = "json"
    MARKDOWN = "markdown"


class ReportResponse(BaseModel):
    """Response model for returning full report"""

    job_id: str
    report: dict[str, Any]  # Full RequirementsReport as dict
