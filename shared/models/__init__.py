"""
TERE4AI Shared Pydantic Models

This package contains all Pydantic models used across the TERE4AI system.
Models are organized by purpose:

  - legal.py: EU AI Act structural representation
  - hleg.py: AI HLEG requirements and subtopics
  - mappings.py: EU AI Act ↔ HLEG alignments
  - citations.py: Traceability citations
  - risk.py: Risk classification output
  - system_description.py: User input representation
  - requirements.py: Generated requirements
  - report.py: Final output report
  - chunks.py: LLM processing chunks
  - mapping_deps.py: Mapping dependencies

Usage:
    from tere4ai.shared.models import (
        Citation, CitationBundle,
        RiskLevel, RiskClassification,
        SystemDescription,
        GeneratedRequirement,
        RequirementsReport,
    )
"""

# Legal document structure
from .legal import (
    Annex,
    Article,
    Chapter,
    Paragraph,
    Point,
    PreprocessedLegalDocument,
    Recital,
    Section,
)

# HLEG requirements
from .hleg import (
    HlegRequirement,
    HlegRequirementSubtopic,
    HlegStructuredDoc,
)

# EU ↔ HLEG mappings
from .mappings import (
    EuRequirementLocation,
    EuToHlegMapping,
    HlegLink,
)

# Citations and traceability
from .citations import (
    CANONICAL_HLEG_IDS,
    Citation,
    CitationBundle,
)

# Risk classification
from .risk import (
    AnnexIIICategory,
    ProhibitedPractice,
    RiskClassification,
    RiskClassificationResult,
    RiskLevel,
)

# System description
from .system_description import (
    AutonomyLevel,
    DataCategory,
    DecisionType,
    DeploymentContext,
    SystemDescription,
    SystemDomain,
)

# Generated requirements
from .requirements import (
    ConflictDetail,
    GeneratedRequirement,
    InvalidCitationDetail,
    RequirementCategory,
    RequirementPriority,
    RequirementType,
    ValidationResult,
)

# Final report
from .report import (
    CoverageMatrix,
    ReportMetrics,
    RequirementsReport,
)

# Chunks (for ingestion)
from .chunks import (
    ChunkResult,
    TextChunk,
)

# Mapping dependencies
from .mapping_deps import (
    EuHlegMappingDeps,
)

__all__ = [
    # Legal
    "Annex",
    "Article",
    "Chapter",
    "Paragraph",
    "Point",
    "PreprocessedLegalDocument",
    "Recital",
    "Section",
    # HLEG
    "HlegRequirement",
    "HlegRequirementSubtopic",
    "HlegStructuredDoc",
    # Mappings
    "EuRequirementLocation",
    "EuToHlegMapping",
    "HlegLink",
    # Citations
    "CANONICAL_HLEG_IDS",
    "Citation",
    "CitationBundle",
    # Risk
    "AnnexIIICategory",
    "ProhibitedPractice",
    "RiskClassification",
    "RiskClassificationResult",
    "RiskLevel",
    # System Description
    "AutonomyLevel",
    "DataCategory",
    "DecisionType",
    "DeploymentContext",
    "SystemDescription",
    "SystemDomain",
    # Requirements
    "ConflictDetail",
    "GeneratedRequirement",
    "InvalidCitationDetail",
    "RequirementCategory",
    "RequirementPriority",
    "RequirementType",
    "ValidationResult",
    # Report
    "CoverageMatrix",
    "ReportMetrics",
    "RequirementsReport",
    # Chunks
    "ChunkResult",
    "TextChunk",
    # Mapping deps
    "EuHlegMappingDeps",
]
