"""
Comprehensive Unit Tests for TERE4AI Phase 4 API Implementation

This module contains thorough tests for:
- api/models.py: AnalyzeRequest, JobStatus, ProcessingPhase, ExportFormat
- api/job_manager.py: JobManager, Job
- api/main.py: API endpoints and helper functions

Test coverage includes:
- Model validation (min/max lengths, enums)
- Job lifecycle management
- API endpoint behavior (success and error paths)
- Markdown report generation
"""

import asyncio
import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import ValidationError

from fastapi.testclient import TestClient

# Import API models
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

# Import JobManager and Job
from api.job_manager import Job, JobManager


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def sample_description():
    """Sample AI system description for testing."""
    return (
        "An AI system for hospital emergency room triage that analyzes patient symptoms, "
        "vital signs, and medical history to prioritize patients and recommend initial "
        "treatment protocols."
    )


@pytest.fixture
def sample_context():
    """Sample context for testing."""
    return "This system will be deployed in European Union hospitals."


@pytest.fixture
def sample_report():
    """Sample completed report for testing export functionality."""
    return {
        "report_id": "test-report-001",
        "generated_at": "2024-01-15T10:30:00",
        "tere4ai_version": "0.1.0",
        "system_description": {
            "domain": "healthcare",
            "purpose": "Patient triage and prioritization",
            "raw_description": "An AI system for hospital emergency room triage..."
        },
        "risk_classification": {
            "level": "high",
            "reasoning": "Healthcare triage affects patient safety",
            "annex_iii_category": "5(a)",
            "applicable_articles": [9, 10, 11, 12, 13],
            "legal_basis": {
                "primary": {
                    "reference_text": "Annex III, Section 5(a)",
                    "quoted_text": "AI systems intended to be used for triage in emergency healthcare"
                }
            }
        },
        "requirements": [
            {
                "id": "REQ-001",
                "title": "Risk Management System",
                "statement": "The system shall implement a risk management system.",
                "category": "risk_management",
                "priority": "critical",
                "requirement_type": "functional",
                "eu_ai_act_citations": [
                    {"reference_text": "Article 9(1)"}
                ],
                "hleg_citations": [
                    {"requirement_id": "technical_robustness", "relevance_score": 0.9}
                ],
                "verification_criteria": [
                    "Risk assessment documentation exists",
                    "Mitigation measures are implemented"
                ]
            }
        ],
        "validation": {
            "article_coverage": 0.85,
            "hleg_coverage": 0.75,
            "is_complete": True,
            "is_consistent": True
        },
        "metrics": {
            "total_citations": 15,
            "unique_articles_cited": 8,
            "unique_hleg_principles_addressed": 5,
            "total_requirements": 1,
            "critical_requirements": 1
        }
    }


@pytest.fixture
def job_manager():
    """Create a fresh JobManager instance for testing."""
    return JobManager(max_jobs=10)


@pytest.fixture
def mock_orchestrator():
    """Mock the orchestrator to avoid running the full pipeline."""
    # The Orchestrator is imported inside run_pipeline, so we need to patch the module it's imported from
    with patch("agents.orchestrator.Orchestrator") as mock_orch_class:
        mock_orchestrator = MagicMock()
        mock_orch_class.return_value = mock_orchestrator

        # Create a mock result
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.total_duration_ms = 1000
        mock_result.traces = []
        mock_result.report = MagicMock()
        mock_result.report.model_dump.return_value = {
            "report_id": "test-123",
            "requirements": [],
            "risk_classification": {"level": "minimal"}
        }

        # Make run return the mock result
        async def mock_run(*args, **kwargs):
            return mock_result

        mock_orchestrator.run = mock_run

        yield mock_orchestrator


@pytest.fixture
def test_client():
    """Create a TestClient for API testing.

    Note: We don't need to mock the orchestrator for most API tests because
    the background task runs asynchronously and we test status/results separately.
    """
    from api.main import app
    return TestClient(app)


# ============================================================================
# MODEL VALIDATION TESTS
# ============================================================================

class TestAnalyzeRequest:
    """Tests for AnalyzeRequest model validation."""

    def test_valid_request(self, sample_description):
        """Test valid AnalyzeRequest creation."""
        request = AnalyzeRequest(description=sample_description)
        assert request.description == sample_description
        assert request.context is None

    def test_valid_request_with_context(self, sample_description, sample_context):
        """Test valid AnalyzeRequest with optional context."""
        request = AnalyzeRequest(
            description=sample_description,
            context=sample_context
        )
        assert request.description == sample_description
        assert request.context == sample_context

    def test_description_min_length_boundary(self):
        """Test description at minimum length (10 characters)."""
        request = AnalyzeRequest(description="A" * 10)
        assert len(request.description) == 10

    def test_description_below_min_length(self):
        """Test description below minimum length raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            AnalyzeRequest(description="Too short")
        errors = exc_info.value.errors()
        assert any("at least 10" in str(e).lower() or "min_length" in str(e).lower()
                   for e in errors)

    def test_description_max_length_boundary(self):
        """Test description at maximum length (10000 characters)."""
        request = AnalyzeRequest(description="A" * 10000)
        assert len(request.description) == 10000

    def test_description_above_max_length(self):
        """Test description above maximum length raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            AnalyzeRequest(description="A" * 10001)
        errors = exc_info.value.errors()
        assert any("at most 10000" in str(e).lower() or "max_length" in str(e).lower()
                   for e in errors)

    def test_context_max_length_boundary(self):
        """Test context at maximum length (5000 characters)."""
        request = AnalyzeRequest(
            description="Valid description for testing",
            context="B" * 5000
        )
        assert len(request.context) == 5000

    def test_context_above_max_length(self):
        """Test context above maximum length raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            AnalyzeRequest(
                description="Valid description for testing",
                context="B" * 5001
            )
        errors = exc_info.value.errors()
        assert any("at most 5000" in str(e).lower() or "max_length" in str(e).lower()
                   for e in errors)

    def test_description_required(self):
        """Test that description field is required."""
        with pytest.raises(ValidationError) as exc_info:
            AnalyzeRequest()
        errors = exc_info.value.errors()
        assert any("description" in str(e).lower() for e in errors)

    def test_empty_description(self):
        """Test that empty description raises ValidationError."""
        with pytest.raises(ValidationError):
            AnalyzeRequest(description="")


class TestJobStatusEnum:
    """Tests for JobStatus enum."""

    def test_all_status_values(self):
        """Test all JobStatus enum values exist."""
        assert JobStatus.PENDING == "pending"
        assert JobStatus.RUNNING == "running"
        assert JobStatus.COMPLETED == "completed"
        assert JobStatus.FAILED == "failed"

    def test_enum_value_count(self):
        """Test that JobStatus has exactly 4 values."""
        assert len(JobStatus) == 4

    def test_status_from_string(self):
        """Test creating JobStatus from string value."""
        assert JobStatus("pending") == JobStatus.PENDING
        assert JobStatus("running") == JobStatus.RUNNING
        assert JobStatus("completed") == JobStatus.COMPLETED
        assert JobStatus("failed") == JobStatus.FAILED


class TestProcessingPhaseEnum:
    """Tests for ProcessingPhase enum."""

    def test_all_phase_values(self):
        """Test all ProcessingPhase enum values exist."""
        assert ProcessingPhase.QUEUED == "queued"
        assert ProcessingPhase.ELICITATION == "elicitation"
        assert ProcessingPhase.ANALYSIS == "analysis"
        assert ProcessingPhase.SPECIFICATION == "specification"
        assert ProcessingPhase.VALIDATION == "validation"
        assert ProcessingPhase.FINALIZING == "finalizing"
        assert ProcessingPhase.COMPLETE == "complete"

    def test_enum_value_count(self):
        """Test that ProcessingPhase has exactly 7 values."""
        assert len(ProcessingPhase) == 7

    def test_phase_from_string(self):
        """Test creating ProcessingPhase from string value."""
        assert ProcessingPhase("queued") == ProcessingPhase.QUEUED
        assert ProcessingPhase("elicitation") == ProcessingPhase.ELICITATION


class TestExportFormatEnum:
    """Tests for ExportFormat enum."""

    def test_all_format_values(self):
        """Test all ExportFormat enum values exist."""
        assert ExportFormat.JSON == "json"
        assert ExportFormat.MARKDOWN == "markdown"

    def test_enum_value_count(self):
        """Test that ExportFormat has exactly 2 values."""
        assert len(ExportFormat) == 2


# ============================================================================
# JOB MANAGER TESTS
# ============================================================================

class TestJob:
    """Tests for the Job dataclass."""

    def test_job_creation(self):
        """Test basic job creation."""
        job = Job(job_id="test-123")
        assert job.job_id == "test-123"
        assert job.status == JobStatus.PENDING
        assert job.phase == ProcessingPhase.QUEUED
        assert job.progress == 0.0
        assert job.message == ""
        assert job.error is None
        assert job.result is None

    def test_job_with_description(self, sample_description):
        """Test job creation with description."""
        job = Job(
            job_id="test-456",
            description=sample_description,
            context="Test context"
        )
        assert job.description == sample_description
        assert job.context == "Test context"

    def test_job_update_status(self):
        """Test job status update."""
        job = Job(job_id="test-789")
        original_updated_at = job.updated_at

        # Small delay to ensure timestamp difference
        import time
        time.sleep(0.01)

        job.update(status=JobStatus.RUNNING)
        assert job.status == JobStatus.RUNNING
        assert job.updated_at > original_updated_at

    def test_job_update_phase(self):
        """Test job phase update."""
        job = Job(job_id="test-update")
        job.update(phase=ProcessingPhase.ELICITATION)
        assert job.phase == ProcessingPhase.ELICITATION

    def test_job_update_progress(self):
        """Test job progress update."""
        job = Job(job_id="test-progress")
        job.update(progress=50.0)
        assert job.progress == 50.0

    def test_job_update_message(self):
        """Test job message update."""
        job = Job(job_id="test-message")
        job.update(message="Processing...")
        assert job.message == "Processing..."

    def test_job_update_error(self):
        """Test job error update."""
        job = Job(job_id="test-error")
        job.update(error="Something went wrong")
        assert job.error == "Something went wrong"

    def test_job_completed_sets_completed_at(self):
        """Test that completing a job sets completed_at timestamp."""
        job = Job(job_id="test-completed")
        assert job.completed_at is None

        job.update(status=JobStatus.COMPLETED)
        assert job.completed_at is not None
        assert isinstance(job.completed_at, datetime)

    def test_job_failed_sets_completed_at(self):
        """Test that failing a job sets completed_at timestamp."""
        job = Job(job_id="test-failed")
        assert job.completed_at is None

        job.update(status=JobStatus.FAILED)
        assert job.completed_at is not None


class TestJobManager:
    """Tests for the JobManager class."""

    @pytest.mark.asyncio
    async def test_create_job(self, job_manager, sample_description):
        """Test creating a new job."""
        job_id = await job_manager.create_job(sample_description)

        assert job_id is not None
        assert len(job_id) == 36  # UUID format

        job = await job_manager.get_job(job_id)
        assert job is not None
        assert job.description == sample_description
        assert job.status == JobStatus.PENDING
        assert job.phase == ProcessingPhase.QUEUED

    @pytest.mark.asyncio
    async def test_create_job_with_context(self, job_manager, sample_description, sample_context):
        """Test creating a job with context."""
        job_id = await job_manager.create_job(sample_description, sample_context)

        job = await job_manager.get_job(job_id)
        assert job.context == sample_context

    @pytest.mark.asyncio
    async def test_get_job_nonexistent(self, job_manager):
        """Test getting a non-existent job returns None."""
        job = await job_manager.get_job("nonexistent-job-id")
        assert job is None

    @pytest.mark.asyncio
    async def test_update_phase(self, job_manager, sample_description):
        """Test updating job phase."""
        job_id = await job_manager.create_job(sample_description)

        await job_manager.update_phase(job_id, ProcessingPhase.ELICITATION)

        job = await job_manager.get_job(job_id)
        assert job.phase == ProcessingPhase.ELICITATION
        assert job.status == JobStatus.RUNNING
        assert job.progress == JobManager.PHASE_PROGRESS[ProcessingPhase.ELICITATION]

    @pytest.mark.asyncio
    async def test_phase_progress_tracking(self, job_manager, sample_description):
        """Test that phase updates correctly update progress."""
        job_id = await job_manager.create_job(sample_description)

        # Test each phase and its expected progress
        phases_to_test = [
            (ProcessingPhase.ELICITATION, 15.0),
            (ProcessingPhase.ANALYSIS, 35.0),
            (ProcessingPhase.SPECIFICATION, 60.0),
            (ProcessingPhase.VALIDATION, 85.0),
            (ProcessingPhase.FINALIZING, 95.0),
        ]

        for phase, expected_progress in phases_to_test:
            await job_manager.update_phase(job_id, phase)
            job = await job_manager.get_job(job_id)
            assert job.progress == expected_progress, f"Phase {phase} should have progress {expected_progress}"

    @pytest.mark.asyncio
    async def test_update_phase_complete(self, job_manager, sample_description):
        """Test that COMPLETE phase sets status to COMPLETED."""
        job_id = await job_manager.create_job(sample_description)

        await job_manager.update_phase(job_id, ProcessingPhase.COMPLETE)

        job = await job_manager.get_job(job_id)
        assert job.phase == ProcessingPhase.COMPLETE
        assert job.status == JobStatus.COMPLETED
        assert job.progress == 100.0

    @pytest.mark.asyncio
    async def test_set_result(self, job_manager, sample_description, sample_report):
        """Test setting job result."""
        job_id = await job_manager.create_job(sample_description)

        await job_manager.set_result(job_id, sample_report)

        job = await job_manager.get_job(job_id)
        assert job.result == sample_report
        assert job.status == JobStatus.COMPLETED
        assert job.phase == ProcessingPhase.COMPLETE
        assert job.progress == 100.0

    @pytest.mark.asyncio
    async def test_set_error(self, job_manager, sample_description):
        """Test setting job error."""
        job_id = await job_manager.create_job(sample_description)
        error_message = "Pipeline failed: Connection timeout"

        await job_manager.set_error(job_id, error_message)

        job = await job_manager.get_job(job_id)
        assert job.status == JobStatus.FAILED
        assert job.error == error_message
        assert "Error:" in job.message

    @pytest.mark.asyncio
    async def test_set_error_long_message_truncated(self, job_manager, sample_description):
        """Test that long error messages are truncated in the message field."""
        job_id = await job_manager.create_job(sample_description)
        long_error = "A" * 200  # Error longer than 100 chars

        await job_manager.set_error(job_id, long_error)

        job = await job_manager.get_job(job_id)
        assert job.error == long_error  # Full error stored
        assert len(job.message) <= 107  # "Error: " + 100 chars

    @pytest.mark.asyncio
    async def test_cleanup_old_jobs_when_max_exceeded(self, sample_description):
        """Test that old completed jobs are cleaned up when max_jobs is exceeded."""
        manager = JobManager(max_jobs=5)

        # Create jobs and complete them
        job_ids = []
        for i in range(5):
            job_id = await manager.create_job(f"{sample_description} - Job {i}")
            await manager.set_result(job_id, {"test": i})
            job_ids.append(job_id)

        assert len(manager.jobs) == 5

        # Create one more job - should trigger cleanup
        new_job_id = await manager.create_job(f"{sample_description} - New Job")

        # Some old completed jobs should be cleaned up
        assert len(manager.jobs) <= 5
        # The new job should exist
        assert await manager.get_job(new_job_id) is not None

    @pytest.mark.asyncio
    async def test_update_nonexistent_job_silently_ignores(self, job_manager):
        """Test that updating a non-existent job doesn't raise an error."""
        # These should not raise exceptions
        await job_manager.update_phase("nonexistent", ProcessingPhase.ELICITATION)
        await job_manager.set_result("nonexistent", {"test": "data"})
        await job_manager.set_error("nonexistent", "error")

    @pytest.mark.asyncio
    async def test_concurrent_job_creation(self, job_manager, sample_description):
        """Test that concurrent job creation is thread-safe."""
        async def create_job():
            return await job_manager.create_job(sample_description)

        # Create 10 jobs concurrently
        tasks = [create_job() for _ in range(10)]
        job_ids = await asyncio.gather(*tasks)

        # All job IDs should be unique
        assert len(set(job_ids)) == 10
        # All jobs should exist
        for job_id in job_ids:
            job = await job_manager.get_job(job_id)
            assert job is not None


# ============================================================================
# API ENDPOINT TESTS
# ============================================================================

class TestHealthEndpoint:
    """Tests for GET /health endpoint."""

    def test_health_check_returns_healthy(self, test_client):
        """Test health check returns healthy status."""
        response = test_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data

    def test_health_check_timestamp_is_valid_iso_format(self, test_client):
        """Test health check timestamp is valid ISO format."""
        response = test_client.get("/health")
        data = response.json()

        # Should parse without error
        timestamp = datetime.fromisoformat(data["timestamp"])
        assert isinstance(timestamp, datetime)


class TestExamplesEndpoint:
    """Tests for GET /api/examples endpoint."""

    def test_get_examples_returns_list(self, test_client):
        """Test examples endpoint returns a list of examples."""
        response = test_client.get("/api/examples")

        assert response.status_code == 200
        data = response.json()
        assert "examples" in data
        assert isinstance(data["examples"], list)

    def test_get_examples_has_four_examples(self, test_client):
        """Test examples endpoint returns exactly 4 examples."""
        response = test_client.get("/api/examples")
        data = response.json()

        assert len(data["examples"]) == 4

    def test_examples_have_required_fields(self, test_client):
        """Test each example has all required fields."""
        response = test_client.get("/api/examples")
        data = response.json()

        required_fields = {"id", "name", "category", "description", "expected_risk_level"}

        for example in data["examples"]:
            assert required_fields.issubset(set(example.keys()))

    def test_examples_cover_all_risk_levels(self, test_client):
        """Test examples cover different risk levels."""
        response = test_client.get("/api/examples")
        data = response.json()

        risk_levels = {ex["expected_risk_level"] for ex in data["examples"]}

        # Should have variety of risk levels
        assert "UNACCEPTABLE" in risk_levels
        assert "HIGH" in risk_levels
        assert "LIMITED" in risk_levels
        assert "MINIMAL" in risk_levels


class TestAnalyzeEndpoint:
    """Tests for POST /api/analyze endpoint."""

    def test_analyze_valid_request(self, test_client, sample_description):
        """Test analyze endpoint with valid request."""
        response = test_client.post(
            "/api/analyze",
            json={"description": sample_description}
        )

        assert response.status_code == 202  # Accepted for async processing
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "pending"
        assert "message" in data

    def test_analyze_with_context(self, test_client, sample_description, sample_context):
        """Test analyze endpoint with optional context."""
        response = test_client.post(
            "/api/analyze",
            json={
                "description": sample_description,
                "context": sample_context
            }
        )

        assert response.status_code == 202  # Accepted for async processing
        data = response.json()
        assert "job_id" in data

    def test_analyze_description_too_short(self, test_client):
        """Test analyze endpoint rejects too short description."""
        response = test_client.post(
            "/api/analyze",
            json={"description": "Short"}
        )

        assert response.status_code == 422  # Validation error

    def test_analyze_description_too_long(self, test_client):
        """Test analyze endpoint rejects too long description."""
        response = test_client.post(
            "/api/analyze",
            json={"description": "A" * 10001}
        )

        assert response.status_code == 422

    def test_analyze_missing_description(self, test_client):
        """Test analyze endpoint requires description."""
        response = test_client.post(
            "/api/analyze",
            json={}
        )

        assert response.status_code == 422

    def test_analyze_context_too_long(self, test_client, sample_description):
        """Test analyze endpoint rejects too long context."""
        response = test_client.post(
            "/api/analyze",
            json={
                "description": sample_description,
                "context": "B" * 5001
            }
        )

        assert response.status_code == 422


class TestStatusEndpoint:
    """Tests for GET /api/status/{job_id} endpoint."""

    def test_status_existing_job(self, test_client, sample_description):
        """Test status endpoint for existing job."""
        # First create a job
        create_response = test_client.post(
            "/api/analyze",
            json={"description": sample_description}
        )
        job_id = create_response.json()["job_id"]

        # Then get status
        response = test_client.get(f"/api/status/{job_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert "status" in data
        assert "phase" in data
        assert "progress" in data
        assert "created_at" in data
        assert "updated_at" in data

    def test_status_nonexistent_job(self, test_client):
        """Test status endpoint returns 404 for non-existent job."""
        response = test_client.get("/api/status/nonexistent-job-id")

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()


class TestReportEndpoint:
    """Tests for GET /api/report/{job_id} endpoint."""

    def test_report_completed_job(self, test_client, sample_description, sample_report):
        """Test report endpoint for completed job."""
        # Create a job
        create_response = test_client.post(
            "/api/analyze",
            json={"description": sample_description}
        )
        job_id = create_response.json()["job_id"]

        # Manually complete the job (simulate background task completion)
        from api.job_manager import job_manager
        import asyncio

        async def set_result():
            await job_manager.set_result(job_id, sample_report)
        asyncio.get_event_loop().run_until_complete(set_result())

        # Get report
        response = test_client.get(f"/api/report/{job_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["report_id"] == sample_report["report_id"]

    def test_report_pending_job(self, sample_description):
        """Test report endpoint returns error for pending job.

        Uses a separate JobManager to avoid background task interference.
        """
        from api.job_manager import job_manager, JobManager, Job
        from api.models import ProcessingPhase, JobStatus
        import asyncio

        # Create a job directly in job_manager without triggering background task
        async def setup_pending_job():
            job_id = await job_manager.create_job(sample_description)
            return job_id

        job_id = asyncio.get_event_loop().run_until_complete(setup_pending_job())

        # Verify job is pending
        async def get_job_status():
            job = await job_manager.get_job(job_id)
            return job.status

        status = asyncio.get_event_loop().run_until_complete(get_job_status())
        assert status == JobStatus.PENDING

        # Now test via API (but don't use POST which triggers background task)
        from api.main import app
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(f"/api/report/{job_id}")

        assert response.status_code == 400
        data = response.json()
        assert "not complete" in data["detail"].lower()

    def test_report_nonexistent_job(self, test_client):
        """Test report endpoint returns 404 for non-existent job."""
        response = test_client.get("/api/report/nonexistent-job-id")

        assert response.status_code == 404


class TestExportEndpoint:
    """Tests for GET /api/export/{job_id}/{format} endpoint."""

    def test_export_json_completed_job(self, test_client, sample_description, sample_report):
        """Test JSON export for completed job."""
        # Create and complete a job
        create_response = test_client.post(
            "/api/analyze",
            json={"description": sample_description}
        )
        job_id = create_response.json()["job_id"]

        from api.job_manager import job_manager
        import asyncio

        async def set_result():
            await job_manager.set_result(job_id, sample_report)
        asyncio.get_event_loop().run_until_complete(set_result())

        # Export as JSON
        response = test_client.get(f"/api/export/{job_id}/json")

        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]
        assert "attachment" in response.headers.get("content-disposition", "")

        data = response.json()
        assert data["report_id"] == sample_report["report_id"]

    def test_export_markdown_completed_job(self, test_client, sample_description, sample_report):
        """Test Markdown export for completed job."""
        # Create and complete a job
        create_response = test_client.post(
            "/api/analyze",
            json={"description": sample_description}
        )
        job_id = create_response.json()["job_id"]

        from api.job_manager import job_manager
        import asyncio

        async def set_result():
            await job_manager.set_result(job_id, sample_report)
        asyncio.get_event_loop().run_until_complete(set_result())

        # Export as Markdown
        response = test_client.get(f"/api/export/{job_id}/markdown")

        assert response.status_code == 200
        assert "text/markdown" in response.headers["content-type"]
        assert "attachment" in response.headers.get("content-disposition", "")

        content = response.text
        assert "# TERE4AI Requirements Report" in content
        assert "Report ID:" in content

    def test_export_pending_job(self, sample_description):
        """Test export endpoint returns error for pending job.

        Uses JobManager directly to create a pending job without triggering background tasks.
        """
        from api.job_manager import job_manager
        from api.models import JobStatus
        import asyncio

        # Create a job directly in job_manager without triggering background task
        async def setup_pending_job():
            job_id = await job_manager.create_job(sample_description)
            return job_id

        job_id = asyncio.get_event_loop().run_until_complete(setup_pending_job())

        # Verify job is pending
        async def get_job_status():
            job = await job_manager.get_job(job_id)
            return job.status

        status = asyncio.get_event_loop().run_until_complete(get_job_status())
        assert status == JobStatus.PENDING

        # Now test via API
        from api.main import app
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(f"/api/export/{job_id}/json")

        assert response.status_code == 400

    def test_export_nonexistent_job(self, test_client):
        """Test export endpoint returns 404 for non-existent job."""
        response = test_client.get("/api/export/nonexistent-job-id/json")

        assert response.status_code == 404

    def test_export_invalid_format(self, test_client, sample_description, sample_report):
        """Test export endpoint returns error for invalid format."""
        # Create and complete a job
        create_response = test_client.post(
            "/api/analyze",
            json={"description": sample_description}
        )
        job_id = create_response.json()["job_id"]

        from api.job_manager import job_manager
        import asyncio

        async def set_result():
            await job_manager.set_result(job_id, sample_report)
        asyncio.get_event_loop().run_until_complete(set_result())

        # Try invalid format
        response = test_client.get(f"/api/export/{job_id}/pdf")

        assert response.status_code == 422  # Validation error for enum


# ============================================================================
# MARKDOWN GENERATION TESTS
# ============================================================================

class TestGenerateMarkdownReport:
    """Tests for the generate_markdown_report helper function."""

    def test_basic_markdown_generation(self, sample_report):
        """Test basic markdown report generation."""
        from api.main import generate_markdown_report

        markdown = generate_markdown_report(sample_report)

        assert isinstance(markdown, str)
        assert len(markdown) > 0
        assert "# TERE4AI Requirements Report" in markdown

    def test_markdown_includes_report_metadata(self, sample_report):
        """Test markdown includes report metadata."""
        from api.main import generate_markdown_report

        markdown = generate_markdown_report(sample_report)

        assert "Generated:" in markdown
        assert "Report ID:" in markdown
        assert "TERE4AI Version:" in markdown

    def test_markdown_includes_system_description(self, sample_report):
        """Test markdown includes system description section."""
        from api.main import generate_markdown_report

        markdown = generate_markdown_report(sample_report)

        assert "## System Description" in markdown
        assert "Domain:" in markdown
        assert "Purpose:" in markdown
        assert "Original Description" in markdown

    def test_markdown_includes_risk_classification(self, sample_report):
        """Test markdown includes risk classification section."""
        from api.main import generate_markdown_report

        markdown = generate_markdown_report(sample_report)

        assert "## Risk Classification" in markdown
        assert "Level:" in markdown
        assert "HIGH" in markdown  # Based on sample_report fixture
        assert "Annex III Category:" in markdown

    def test_markdown_includes_requirements(self, sample_report):
        """Test markdown includes requirements section."""
        from api.main import generate_markdown_report

        markdown = generate_markdown_report(sample_report)

        assert "## Generated Requirements" in markdown
        assert "Total Requirements:" in markdown
        assert "REQ-001" in markdown
        assert "Risk Management System" in markdown

    def test_markdown_includes_validation(self, sample_report):
        """Test markdown includes validation results section."""
        from api.main import generate_markdown_report

        markdown = generate_markdown_report(sample_report)

        assert "## Validation Results" in markdown
        assert "Article Coverage:" in markdown
        assert "HLEG Coverage:" in markdown

    def test_markdown_includes_metrics(self, sample_report):
        """Test markdown includes metrics section."""
        from api.main import generate_markdown_report

        markdown = generate_markdown_report(sample_report)

        assert "## Report Metrics" in markdown
        assert "Total Citations:" in markdown
        assert "Unique Articles Cited:" in markdown

    def test_markdown_includes_footer(self, sample_report):
        """Test markdown includes footer."""
        from api.main import generate_markdown_report

        markdown = generate_markdown_report(sample_report)

        assert "Generated by TERE4AI" in markdown
        assert "REFSQ 2026" in markdown

    def test_markdown_with_unacceptable_risk(self):
        """Test markdown generation for unacceptable risk level."""
        from api.main import generate_markdown_report

        report = {
            "report_id": "test-unacceptable",
            "generated_at": "2024-01-15T10:30:00",
            "tere4ai_version": "0.1.0",
            "risk_classification": {
                "level": "unacceptable",
                "reasoning": "Prohibited practice",
                "prohibited_practice": "a",
                "prohibition_details": "Social scoring system",
                "legal_basis": {
                    "primary": {
                        "reference_text": "Article 5(1)(a)",
                        "quoted_text": "Prohibited practices"
                    }
                }
            },
            "requirements": []
        }

        markdown = generate_markdown_report(report)

        assert "UNACCEPTABLE" in markdown
        assert "PROHIBITED" in markdown
        assert "Article 5(1)" in markdown

    def test_markdown_with_empty_requirements(self):
        """Test markdown generation with no requirements."""
        from api.main import generate_markdown_report

        report = {
            "report_id": "test-empty",
            "generated_at": "2024-01-15T10:30:00",
            "tere4ai_version": "0.1.0",
            "risk_classification": {
                "level": "minimal",
                "reasoning": "Low risk system"
            },
            "requirements": []
        }

        markdown = generate_markdown_report(report)

        # Should still generate valid markdown even without requirements
        assert "# TERE4AI Requirements Report" in markdown

    def test_markdown_handles_missing_fields(self):
        """Test markdown generation handles missing optional fields gracefully."""
        from api.main import generate_markdown_report

        minimal_report = {
            "report_id": "test-minimal",
            "generated_at": "2024-01-15T10:30:00",
        }

        markdown = generate_markdown_report(minimal_report)

        assert "# TERE4AI Requirements Report" in markdown
        assert "N/A" in markdown  # Default for missing values

    def test_markdown_requirement_citations(self, sample_report):
        """Test markdown includes requirement citations."""
        from api.main import generate_markdown_report

        markdown = generate_markdown_report(sample_report)

        assert "EU AI Act Citations:" in markdown
        assert "HLEG Alignment:" in markdown
        assert "Verification Criteria:" in markdown


# ============================================================================
# INTEGRATION TESTS (API + JobManager)
# ============================================================================

class TestAPIJobManagerIntegration:
    """Integration tests for API endpoints with JobManager."""

    def test_job_lifecycle(self, sample_description, sample_report):
        """Test complete job lifecycle through API.

        Creates a job directly via JobManager and tests status/report/export endpoints.
        This avoids background task timing issues.
        """
        from api.job_manager import job_manager
        from api.main import app
        import asyncio

        client = TestClient(app, raise_server_exceptions=False)

        # 1. Create job directly via job_manager (not API, to control timing)
        async def create_job():
            return await job_manager.create_job(sample_description)

        job_id = asyncio.get_event_loop().run_until_complete(create_job())
        assert job_id is not None

        # 2. Check initial status
        status_response = client.get(f"/api/status/{job_id}")
        assert status_response.status_code == 200
        assert status_response.json()["status"] == "pending"

        # 3. Simulate phase transitions
        async def simulate_pipeline():
            await job_manager.update_phase(job_id, ProcessingPhase.ELICITATION)
            await job_manager.update_phase(job_id, ProcessingPhase.ANALYSIS)
            await job_manager.update_phase(job_id, ProcessingPhase.SPECIFICATION)
            await job_manager.update_phase(job_id, ProcessingPhase.VALIDATION)
            await job_manager.set_result(job_id, sample_report)

        asyncio.get_event_loop().run_until_complete(simulate_pipeline())

        # 4. Check completed status
        status_response = client.get(f"/api/status/{job_id}")
        assert status_response.json()["status"] == "completed"
        assert status_response.json()["progress"] == 100.0

        # 5. Get report
        report_response = client.get(f"/api/report/{job_id}")
        assert report_response.status_code == 200

        # 6. Export
        export_response = client.get(f"/api/export/{job_id}/json")
        assert export_response.status_code == 200

    def test_analyze_endpoint_creates_job(self, test_client, sample_description):
        """Test that POST /api/analyze creates a job and returns job_id."""
        response = test_client.post(
            "/api/analyze",
            json={"description": sample_description}
        )

        assert response.status_code == 202  # Accepted for async processing
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "pending"
        assert len(data["job_id"]) == 36  # UUID format
