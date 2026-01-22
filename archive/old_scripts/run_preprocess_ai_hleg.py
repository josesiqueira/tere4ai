"""
Step: Preprocess AI HLEG Guidelines & Ingest Requirements into Neo4j

This script:
  1. Reads the AI HLEG guidelines text from data/ai_hleg.txt
  2. Uses the hleg_preprocess_agent (GPT-5-nano) to extract the
     seven requirements of Trustworthy AI
  3. Performs a basic sanity check (exactly 7 requirements)
  4. Ingests the structured result into Neo4j

This mirrors the design of the EU AI Act preprocessing pipeline:
  - LLM-only for semantic extraction
  - Deterministic metadata via deps
  - Deterministic Neo4j writes via ingest_hleg.py
"""

import asyncio
import time
from pathlib import Path

from dotenv import load_dotenv
from pydantic_ai import exceptions

from agent_hleg_preprocess import hleg_preprocess_agent
from models.hleg_preprocess import HlegPreprocessDeps
from models.ai_hleg import HlegStructuredDoc
from ingest_hleg import ingest_hleg_document
from config.neo4j_config import verify_connection


# Load environment variables from .env file (for OPENAI_API_KEY, Neo4j config)
load_dotenv()


async def preprocess_ai_hleg() -> HlegStructuredDoc:
    """
    Preprocess the AI HLEG guidelines into a HlegStructuredDoc.
    """
    # Configuration for this document
    DOCUMENT_ID = "ai_hleg_2019"
    SOURCE_FILE = "data/ai_hleg.txt"
    YEAR = 2019

    file_path = Path(SOURCE_FILE)
    if not file_path.exists():
        raise FileNotFoundError(
            f"AI HLEG source file not found: {SOURCE_FILE} "
            "(expected at project_root/data/ai_hleg.txt)"
        )

    raw_text = file_path.read_text(encoding="utf-8")

    # Build a clear prompt
    prompt = (
        "You will receive the full text of the AI HLEG 'Ethics Guidelines for Trustworthy AI'.\n"
        "Your task is to extract the seven requirements of Trustworthy AI as "
        "a structured HlegStructuredDoc.\n\n"
        "Full text:\n"
        f"{raw_text}"
    )

    deps = HlegPreprocessDeps(
        document_id=DOCUMENT_ID,
        source_file=SOURCE_FILE,
        year=YEAR,
    )

    # Retry logic for validation errors (LLM not following schema correctly)
    max_retries = 5
    for attempt in range(max_retries):
        try:
            result = await hleg_preprocess_agent.run(prompt, deps=deps)
            return result.output
        except exceptions.UnexpectedModelBehavior as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** (attempt + 1)  # 2s, 4s, 8s, 16s, 32s
                print(
                    f"  ⚠️ Validation/output schema error (attempt {attempt + 1}/{max_retries}). "
                    f"Retrying in {wait_time}s..."
                )
                print(f"     Error: {str(e)[:200]}...")
                await asyncio.sleep(wait_time)
                continue
            # Final attempt failed
            print(f"❌ Failed after {max_retries} attempts")
            raise


async def main() -> None:
    """
    Main entrypoint for AI HLEG preprocessing and ingestion.
    """
    start_time = time.time()

    print("Prerequisites:")
    print("  ✓ OPENAI_API_KEY in .env file")
    print("  ✓ Neo4j running and reachable (URI/creds from .env)")
    print("  ✓ data/ai_hleg.txt present\n")

    # Verify Neo4j connection (optional but helpful for debugging)
    if not verify_connection():
        print("❌ Neo4j connection failed. Please check config.neo4j_config and Docker.")
        return
    else:
        print("✓ Neo4j connection verified.\n")

    print("=" * 70)
    print("AI HLEG - PREPROCESSING & INGESTION")
    print("=" * 70)
    print(
        "This script extracts the seven requirements of Trustworthy AI\n"
        "from the AI HLEG 'Ethics Guidelines for Trustworthy AI' and "
        "ingests them into Neo4j.\n"
    )
    
    print("[1/2] Running AI HLEG preprocessing agent (GPT-5-nano)...\n")

    try:
        doc = await preprocess_ai_hleg()
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return
    except Exception as e:
        print(f"❌ Preprocessing failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # Basic sanity check: we expect exactly 7 requirements
    num_reqs = len(doc.requirements)
    print(f"✓ Preprocessing completed. Found {num_reqs} requirements.\n")

    if num_reqs != 7:
        print("⚠️  Sanity check FAILED: expected 7 requirements, "
              f"but got {num_reqs}.")
        print("    For trustworthiness, we will NOT ingest this result.")
        print("    Please inspect the agent output and instructions.")
        return

    print("[2/2] Ingesting HLEG requirements into Neo4j...\n")
    try:
        ingest_hleg_document(doc)
    except Exception as e:
        print(f"❌ Ingestion failed: {e}")
        import traceback
        traceback.print_exc()
        return

    print()
    print("=" * 70)
    print("✓ AI HLEG PREPROCESSING & INGESTION COMPLETE")
    print("=" * 70)
    print()
    print("You can now explore the graph in Neo4j, e.g.:")
    print("  MATCH (h:HLEG)-[:HAS_REQUIREMENT]->(r:HLEGRequirement)")
    print("  RETURN h, r;")
    print()
    print("These HLEGRequirement nodes can later be linked to:")
    print("  - EU AI Act obligations (articles, annexes)")
    print("  - Incident assessments")
    print("to support your PhD research on trustworthy AI systems.")
    print()

    # Display elapsed time
    elapsed_time = time.time() - start_time
    minutes = int(elapsed_time // 60)
    seconds = elapsed_time % 60
    print("=" * 70)
    print(f"⏱️  Total processing time: {minutes}m {seconds:.2f}s")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
