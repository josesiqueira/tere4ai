"""
TERE4AI FastAPI Application

Main API server for the Trustworthy Ethical Requirements Engineering for AI tool.
Provides endpoints for:
  - Analyzing AI system descriptions
  - Tracking job progress
  - Exporting reports
  - Getting example system descriptions
"""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from api.job_manager import Job, JobManager, job_manager
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("tere4ai.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    logger.info("Starting TERE4AI API server")
    yield
    logger.info("Shutting down TERE4AI API server")


# Create FastAPI app
app = FastAPI(
    title="TERE4AI API",
    description="Trustworthy Ethical Requirements Engineering for AI - REFSQ 2026",
    version="0.1.0",
    lifespan=lifespan,
)

# Configure CORS for frontend (configurable via environment)
cors_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Mount static files for frontend
static_path = Path(__file__).parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=static_path), name="static")


# ============================================================================
# Pipeline Execution
# ============================================================================

async def run_pipeline(job_id: str, description: str, context: str | None):
    """Run the TERE4AI pipeline as a background task"""
    try:
        # Import here to avoid circular imports and allow lazy loading
        from agents.orchestrator import Orchestrator

        logger.info(f"Starting pipeline for job {job_id}")

        # Create orchestrator
        orchestrator = Orchestrator()

        # Progress callback that updates job manager
        async def progress_callback(phase: str, message: str = ""):
            phase_map = {
                "elicitation": ProcessingPhase.ELICITATION,
                "analysis": ProcessingPhase.ANALYSIS,
                "specification": ProcessingPhase.SPECIFICATION,
                "validation": ProcessingPhase.VALIDATION,
                "complete": ProcessingPhase.FINALIZING,
            }
            if phase in phase_map:
                await job_manager.update_phase(job_id, phase_map[phase])
                # Also update the message if provided
                job = await job_manager.get_job(job_id)
                if job and message:
                    job.message = message

        # Run the pipeline with progress callback
        result = await orchestrator.run(description, context, progress_callback=progress_callback)

        # Convert report to dict for storage
        report_dict = result.report.model_dump(mode="json")

        # Add execution metadata
        report_dict["_execution"] = {
            "job_id": job_id,
            "duration_ms": result.total_duration_ms,
            "success": result.success,
            "trace_count": len(result.traces),
        }

        # Store result
        await job_manager.set_result(job_id, report_dict)

        logger.info(f"Pipeline completed for job {job_id}")

    except Exception as e:
        logger.exception(f"Pipeline failed for job {job_id}: {e}")
        await job_manager.set_error(job_id, str(e))


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint - redirect to frontend"""
    return FileResponse(static_path / "index.html") if static_path.exists() else {
        "name": "TERE4AI API",
        "version": "0.1.0",
        "docs": "/docs",
    }


@app.post("/api/analyze", response_model=AnalyzeResponse, status_code=202)
async def analyze(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    """
    Analyze an AI system description.

    Starts an async job that runs through the RE pipeline:
      1. Elicitation - Extract system characteristics
      2. Analysis - Classify risk level
      3. Specification - Generate requirements (if applicable)
      4. Validation - Validate completeness

    Returns a job ID for tracking progress via GET /api/status/{job_id}
    """
    # Create job
    job_id = await job_manager.create_job(request.description, request.context)

    # Start background processing
    background_tasks.add_task(run_pipeline, job_id, request.description, request.context)

    return AnalyzeResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        message="Analysis job created. Poll /api/status/{job_id} for progress.",
    )


@app.get("/api/status/{job_id}", response_model=JobStatusResponse)
async def get_status(job_id: str):
    """
    Get the status of an analysis job.

    Returns current phase, progress percentage (0-100), and status message.
    Poll this endpoint to update the progress bar in the UI.
    """
    job = await job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        phase=job.phase,
        progress=job.progress,
        message=job.message,
        created_at=job.created_at,
        updated_at=job.updated_at,
        completed_at=job.completed_at,
        error=job.error,
    )


@app.get("/api/report/{job_id}")
async def get_report(job_id: str) -> dict[str, Any]:
    """
    Get the full analysis report for a completed job.

    Only available after the job status is COMPLETED.
    """
    job = await job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Job is not complete. Current status: {job.status.value}"
        )

    if not job.result:
        raise HTTPException(status_code=500, detail="Job completed but no result available")

    return job.result


@app.get("/api/export/{job_id}/{format}")
async def export_report(job_id: str, format: ExportFormat):
    """
    Export the analysis report in the specified format.

    Supported formats:
      - json: Full JSON export
      - markdown: Human-readable markdown report
    """
    job = await job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Job is not complete. Current status: {job.status.value}"
        )

    if not job.result:
        raise HTTPException(status_code=500, detail="Job completed but no result available")

    if format == ExportFormat.JSON:
        return JSONResponse(
            content=job.result,
            headers={
                "Content-Disposition": f'attachment; filename="tere4ai_report_{job_id[:8]}.json"'
            },
        )

    elif format == ExportFormat.MARKDOWN:
        markdown = generate_markdown_report(job.result)
        return Response(
            content=markdown,
            media_type="text/markdown",
            headers={
                "Content-Disposition": f'attachment; filename="tere4ai_report_{job_id[:8]}.md"'
            },
        )

    raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")


@app.get("/api/examples", response_model=ExamplesResponse)
async def get_examples():
    """
    Get example AI system descriptions for testing.

    Returns 4 examples covering different risk levels:
      - Unacceptable (prohibited)
      - High-risk (healthcare)
      - Limited risk (chatbot)
      - Minimal risk (recommendation)
    """
    examples = [
        ExampleSystem(
            id="prohibited",
            name="Deepfake Generator",
            category="Unacceptable Risk",
            description=(
                "An AI application that generates realistic nude images of people based on "
                "their regular photos, allowing users to create intimate content without the "
                "subject's knowledge or consent."
            ),
            expected_risk_level="UNACCEPTABLE",
        ),
        ExampleSystem(
            id="high-risk-healthcare",
            name="Hospital Triage System",
            category="High Risk - Healthcare",
            description=(
                "An AI system for hospital emergency room triage that analyzes patient symptoms, "
                "vital signs, and medical history to prioritize patients and recommend initial "
                "treatment protocols. The system assists medical staff in making time-critical "
                "decisions about patient care priority."
            ),
            expected_risk_level="HIGH",
        ),
        ExampleSystem(
            id="limited-risk",
            name="E-commerce Chatbot",
            category="Limited Risk",
            description=(
                "A customer service chatbot that handles common inquiries about products, "
                "shipping, and returns for an e-commerce store. The chatbot uses natural "
                "language processing to understand customer questions and provide helpful "
                "responses about order status and store policies."
            ),
            expected_risk_level="LIMITED",
        ),
        ExampleSystem(
            id="minimal-risk",
            name="Movie Recommender",
            category="Minimal Risk",
            description=(
                "An AI recommendation system that suggests movies to users based on their "
                "viewing history, ratings, and preferences for a streaming platform. The "
                "system personalizes content discovery without making any consequential "
                "decisions about users."
            ),
            expected_risk_level="MINIMAL",
        ),
    ]

    return ExamplesResponse(examples=examples)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


# ============================================================================
# Report Generation Helpers
# ============================================================================

def generate_markdown_report(report: dict[str, Any]) -> str:
    """Generate a markdown report from the RequirementsReport dict"""
    lines = []

    # Header
    lines.append("# TERE4AI Requirements Report")
    lines.append("")
    lines.append(f"**Generated:** {report.get('generated_at', 'N/A')}")
    lines.append(f"**Report ID:** {report.get('report_id', 'N/A')}")
    lines.append(f"**TERE4AI Version:** {report.get('tere4ai_version', 'N/A')}")
    lines.append("")

    # System Description
    sys_desc = report.get("system_description")
    if sys_desc:
        lines.append("---")
        lines.append("## System Description")
        lines.append("")
        lines.append(f"**Domain:** {sys_desc.get('domain', 'N/A')}")
        lines.append(f"**Purpose:** {sys_desc.get('purpose', 'N/A')}")
        lines.append("")
        lines.append("### Original Description")
        lines.append(f"> {sys_desc.get('raw_description', 'N/A')}")
        lines.append("")

    # Risk Classification
    risk = report.get("risk_classification")
    if risk:
        lines.append("---")
        lines.append("## Risk Classification")
        lines.append("")
        level = risk.get("level", "N/A")
        lines.append(f"### Level: **{level.upper()}**")
        lines.append("")

        if level == "unacceptable":
            lines.append("⛔ **This system is PROHIBITED under the EU AI Act.**")
            lines.append("")
            if risk.get("prohibited_practice"):
                lines.append(f"**Prohibited Practice:** Article 5(1)({risk.get('prohibited_practice', '')})")
            if risk.get("prohibition_details"):
                lines.append(f"**Details:** {risk.get('prohibition_details')}")

        elif level == "high":
            lines.append("⚠️ **This system is classified as HIGH-RISK.**")
            lines.append("")
            if risk.get("annex_iii_category"):
                lines.append(f"**Annex III Category:** {risk.get('annex_iii_category')}")
            if risk.get("applicable_articles"):
                articles = risk.get("applicable_articles", [])
                lines.append(f"**Applicable Articles:** {', '.join(str(a) for a in articles)}")

        lines.append("")
        lines.append("### Legal Basis")
        legal_basis = risk.get("legal_basis", {})
        primary = legal_basis.get("primary", {})
        if primary:
            lines.append(f"**Primary:** {primary.get('reference_text', 'N/A')}")
            if primary.get("quoted_text"):
                lines.append(f"> \"{primary.get('quoted_text')}\"")
        lines.append("")
        lines.append(f"**Reasoning:** {risk.get('reasoning', 'N/A')}")
        lines.append("")

    # Requirements
    requirements = report.get("requirements", [])
    if requirements:
        lines.append("---")
        lines.append("## Generated Requirements")
        lines.append("")
        lines.append(f"**Total Requirements:** {len(requirements)}")
        lines.append("")

        for req in requirements:
            lines.append(f"### {req.get('id', 'N/A')}: {req.get('title', 'N/A')}")
            lines.append("")
            lines.append(f"**Statement:** {req.get('statement', 'N/A')}")
            lines.append("")
            lines.append(f"- **Category:** {req.get('category', 'N/A')}")
            lines.append(f"- **Priority:** {req.get('priority', 'N/A')}")
            lines.append(f"- **Type:** {req.get('requirement_type', 'N/A')}")
            lines.append("")

            # EU AI Act citations
            eu_cites = req.get("eu_ai_act_citations", [])
            if eu_cites:
                lines.append("**EU AI Act Citations:**")
                for cite in eu_cites:
                    ref = cite.get("reference_text", "N/A")
                    lines.append(f"- {ref}")
                lines.append("")

            # HLEG citations
            hleg_cites = req.get("hleg_citations", [])
            if hleg_cites:
                lines.append("**HLEG Alignment:**")
                for cite in hleg_cites:
                    req_id = cite.get("requirement_id", "N/A")
                    score = cite.get("relevance_score", 0)
                    lines.append(f"- {req_id} (relevance: {score:.2f})")
                lines.append("")

            # Verification
            verification = req.get("verification_criteria", [])
            if verification:
                lines.append("**Verification Criteria:**")
                for v in verification:
                    lines.append(f"- {v}")
                lines.append("")

            lines.append("---")
            lines.append("")

    # Validation
    validation = report.get("validation")
    if validation:
        lines.append("## Validation Results")
        lines.append("")
        lines.append(f"- **Article Coverage:** {validation.get('article_coverage', 0) * 100:.1f}%")
        lines.append(f"- **HLEG Coverage:** {validation.get('hleg_coverage', 0) * 100:.1f}%")
        lines.append(f"- **Complete:** {'Yes' if validation.get('is_complete') else 'No'}")
        lines.append(f"- **Consistent:** {'Yes' if validation.get('is_consistent') else 'No'}")
        lines.append("")

    # Metrics
    metrics = report.get("metrics", {})
    if metrics:
        lines.append("## Report Metrics")
        lines.append("")
        lines.append(f"- **Total Citations:** {metrics.get('total_citations', 0)}")
        lines.append(f"- **Unique Articles Cited:** {metrics.get('unique_articles_cited', 0)}")
        lines.append(f"- **HLEG Principles Addressed:** {metrics.get('unique_hleg_principles_addressed', 0)}")
        lines.append(f"- **Total Requirements:** {metrics.get('total_requirements', 0)}")
        lines.append(f"- **Critical Requirements:** {metrics.get('critical_requirements', 0)}")
        lines.append("")

    # Footer
    lines.append("---")
    lines.append("*Generated by TERE4AI - Trustworthy Ethical Requirements Engineering for AI*")
    lines.append("*Target: REFSQ 2026*")

    return "\n".join(lines)


# ============================================================================
# Entry Point
# ============================================================================

def main():
    """Run the API server"""
    import uvicorn

    host = os.environ.get("TERE4AI_HOST", "0.0.0.0")
    port = int(os.environ.get("TERE4AI_PORT", "8000"))

    uvicorn.run(
        "api.main:app",
        host=host,
        port=port,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
