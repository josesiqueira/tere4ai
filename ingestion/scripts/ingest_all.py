"""
TERE4AI - Complete Data Ingestion Pipeline

Ingests all data into Neo4j:
1. EU AI Act (articles, paragraphs, recitals, annexes)
2. HLEG Trustworthy AI Guidelines (7 principles + subtopics)
3. Semantic mappings between EU AI Act and HLEG

Usage:
    python -m ingestion.scripts.ingest_all
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("tere4ai.ingestion")


def check_environment():
    """Check that required environment variables are set"""
    required = ["NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD"]
    missing = [var for var in required if not os.environ.get(var)]

    if missing:
        logger.error(f"Missing environment variables: {', '.join(missing)}")
        logger.error("Please set them in .env file or environment")
        sys.exit(1)

    logger.info("Environment configuration OK")


async def run_ingestion():
    """Run the complete ingestion pipeline"""
    from ingestion.scripts.ingest_eu_ai_act import ingest_eu_ai_act
    from ingestion.scripts.ingest_hleg import ingest_hleg
    from ingestion.scripts.create_mappings import create_mappings

    logger.info("=" * 60)
    logger.info("TERE4AI - Data Ingestion Pipeline")
    logger.info("=" * 60)

    # Step 1: Ingest EU AI Act
    logger.info("")
    logger.info("[1/3] Ingesting EU AI Act...")
    try:
        await ingest_eu_ai_act()
        logger.info("EU AI Act ingestion complete")
    except Exception as e:
        logger.error(f"EU AI Act ingestion failed: {e}")
        raise

    # Step 2: Ingest HLEG Guidelines
    logger.info("")
    logger.info("[2/3] Ingesting HLEG Trustworthy AI Guidelines...")
    try:
        await ingest_hleg()
        logger.info("HLEG ingestion complete")
    except Exception as e:
        logger.error(f"HLEG ingestion failed: {e}")
        raise

    # Step 3: Create semantic mappings
    logger.info("")
    logger.info("[3/3] Creating EU AI Act ↔ HLEG mappings...")
    try:
        await create_mappings()
        logger.info("Mapping creation complete")
    except Exception as e:
        logger.error(f"Mapping creation failed: {e}")
        raise

    logger.info("")
    logger.info("=" * 60)
    logger.info("Ingestion pipeline completed successfully!")
    logger.info("=" * 60)


def main():
    """Entry point"""
    # Load environment from .env if available
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).parent.parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            logger.info(f"Loaded environment from {env_path}")
    except ImportError:
        logger.warning("python-dotenv not installed, using system environment")

    # Check environment
    check_environment()

    # Run ingestion
    asyncio.run(run_ingestion())


if __name__ == "__main__":
    main()
