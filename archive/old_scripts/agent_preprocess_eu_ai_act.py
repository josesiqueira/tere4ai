"""
Structural Preprocessing Agent for the EU AI Act (OPTIMIZED)

Extracts physical structure from EU AI Act text into Pydantic models.
Simplified prompt for better extraction reliability.
"""

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel

from models.legal_structure import PreprocessedLegalDocument
from models.legal_preprocess import LegalPreprocessDeps
from models.legal_chunks import ChunkResult

load_dotenv()

# ============================================================================
# LLM Model Configuration
# ============================================================================
model = OpenAIChatModel(model_name="gpt-5-nano")


# ============================================================================
# Chunk-level Preprocessing Agent (OPTIMIZED - ~3k tokens instead of ~8.5k)
# ============================================================================

preprocess_legal_chunk_agent = Agent[LegalPreprocessDeps, ChunkResult](
    model,
    deps_type=LegalPreprocessDeps,
    output_type=ChunkResult,
    retries=3,  # Increase from default 1 for output validation errors
    instructions="""You are a legal document parser. Extract the COMPLETE structure from this EU AI Act chunk.

⚠️ CRITICAL: You MUST extract EVERY article in the text. Do NOT stop after the first few articles.

EXTRACTION PROCESS:
1. First, scan the ENTIRE text and identify ALL "Article N" headings (e.g., Article 6, Article 7, ...)
2. For EACH article found, extract its complete content including ALL paragraphs
3. Continue until you reach the END of the text - do not stop early

SCHEMA (use these exact field names and types):
- Recital: number (int), text (string)
- Chapter: number (string like "I", "II"), title (string), sections (array), articles (array)
- Section: number (string like "1", "2"), title (string), articles (array)
- Article: number (int), title (string), paragraphs (array)
- Paragraph: index (int), text (string), points (array)
- Point: marker (string like "a", "b"), text (string)
- Annex: number (string), title (string), raw_text (string)

KEY TYPE RULES:
- Article.number and Paragraph.index are INTEGERS (1, 2, 3)
- Chapter.number and Section.number are STRINGS ("I", "II", "1", "2")
- Never use "title" or "number" on Paragraph - use "index" and "text"

OUTPUT by chunk kind:
- kind='recitals': Fill recitals array only
- kind='chapter': Fill chapter object only, set sections=[] if no SECTION headings
- kind='section': Fill section object only
- kind='annex': Fill annex object only

COMPLETENESS CHECK: Before returning, verify you extracted ALL articles mentioned in the text.
""",
)


# Legacy agent kept for compatibility (not used in chunked processing)
preprocess_legal_agent = Agent[LegalPreprocessDeps, PreprocessedLegalDocument](
    model,
    deps_type=LegalPreprocessDeps,
    output_type=PreprocessedLegalDocument,
    instructions="Extract EU AI Act structure into PreprocessedLegalDocument. Follow schema exactly.",
)
