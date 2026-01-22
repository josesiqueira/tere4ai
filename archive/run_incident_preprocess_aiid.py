"""
AI Incident Database Preprocessing Script

This script preprocesses AI Incident Database-style incidents into structured
AIIncident objects and ingests them into Neo4j.

Workflow:
1. Read incident data (currently hardcoded samples, can be extended to CSV)
2. Compute text sanity stats for each incident description
3. Use LLM agent to structure each incident into AIIncident
4. Ingest structured incidents into Neo4j deterministically
5. Print summary

The script uses hardcoded sample incidents for initial testing. To extend to CSV:
  - Add pandas import: import pandas as pd
  - Load CSV: df = pd.read_csv("ai_incidents.csv")
  - Iterate rows: for idx, row in df.iterrows():

Usage:
    python run_incident_preprocess_aiid.py

Prerequisites:
  - OPENAI_API_KEY in .env file
  - Neo4j running on localhost:7687 (or configured in .env)
"""

import asyncio
from models.incidents import AIIncident, SourceInfo
from agent_incident_preprocess import incident_preprocess_agent, IncidentPreprocessDeps
from ingest_incident import ingest_incident
from text_sanity import compute_text_stats, print_text_stats


# ============================================================================
# Sample Incident Data (Hardcoded for Testing)
# ============================================================================

# These are example incidents inspired by real AI incidents
# In production, replace with CSV loading or API fetching
SAMPLE_INCIDENTS = [
    {
        "Incident ID": "1",
        "Title": "Google YouTube Kids Exposes Children to Disturbing Content",
        "Description": "YouTube's content recommendation algorithm exposed children to disturbing and inappropriate content including graphic violence and sexual content, despite the content being labeled as 'YouTube Kids'. The platform's AI-driven recommendation system failed to adequately filter harmful content, putting children at risk of exposure to material unsuitable for their age group.",
        "Date": "2017-11-04",
        "Alleged Deployer": "Google",
        "Alleged Developer": "Google",
        "Alleged Harmed Parties": "Children, Parents",
        "Implicated Systems": "YouTube recommendation algorithm"
    },
    {
        "Incident ID": "2",
        "Title": "Uber Self-Driving Car Kills Pedestrian in Arizona",
        "Description": "An Uber autonomous vehicle struck and killed a pedestrian crossing the street in Tempe, Arizona. The self-driving system failed to properly detect and respond to the pedestrian, and the human safety driver was distracted. This was the first known fatality involving a fully autonomous vehicle striking a pedestrian.",
        "Date": "2018-03-18",
        "Alleged Deployer": "Uber",
        "Alleged Developer": "Uber ATG",
        "Alleged Harmed Parties": "Elaine Herzberg (deceased pedestrian)",
        "Implicated Systems": "Uber autonomous driving system"
    },
    {
        "Incident ID": "3",
        "Title": "Microsoft Tay Chatbot Posts Offensive Content",
        "Description": "Microsoft's AI chatbot 'Tay' was designed to learn from Twitter interactions but quickly began posting offensive, racist, and inflammatory content after being manipulated by malicious users. The bot had to be shut down within 24 hours of launch due to its increasingly inappropriate responses.",
        "Date": "2016-03-23",
        "Alleged Deployer": "Microsoft",
        "Alleged Developer": "Microsoft",
        "Alleged Harmed Parties": "Twitter users, Microsoft",
        "Implicated Systems": "Tay chatbot, Twitter learning algorithm"
    },
]


# ============================================================================
# Incident Preprocessing Functions
# ============================================================================

async def preprocess_one_incident_row(row: dict, idx: int) -> AIIncident:
    """
    Preprocess one incident row using the LLM agent.

    Args:
        row: Dictionary with incident fields (Incident ID, Title, Description, etc.)
        idx: Row index for logging

    Returns:
        AIIncident object with structured data

    Workflow:
        1. Build deterministic metadata (deps)
        2. Compute text sanity stats on description
        3. Build prompt with all incident fields
        4. Call incident_preprocess_agent
        5. Return structured AIIncident
    """
    # Build deterministic metadata
    # These IDs are provided by the caller and must be echoed back by the agent
    incident_id = f"incident_{int(row['Incident ID']):04d}"
    deps = IncidentPreprocessDeps(
        incident_id=incident_id,
        source_db="AI Incident Database",
        source_id=row["Incident ID"],
        source_url=None,  # Add URL if available in data
    )

    # Compute text sanity stats for the incident description
    # This provides transparency about the size and content of the incident text
    description_text = row.get("Description", "")
    if description_text:
        stats = compute_text_stats(
            description_text,
            source_type="AI_INCIDENT",
            source_id=incident_id
        )
        print_text_stats(stats)

    # Build prompt with all available fields
    # The agent will extract structured data from this
    prompt = f"""Process this AI incident:

Title: {row.get('Title', '')}

Description:
{row.get('Description', '')}

Date: {row.get('Date', 'Unknown')}
Alleged Deployer: {row.get('Alleged Deployer', 'Unknown')}
Alleged Developer: {row.get('Alleged Developer', 'Unknown')}
Alleged Harmed Parties: {row.get('Alleged Harmed Parties', 'Unknown')}
Implicated Systems: {row.get('Implicated Systems', 'Unknown')}

Please structure this into an AIIncident object.
"""

    print(f"\n[{idx + 1}/{len(SAMPLE_INCIDENTS)}] Processing incident '{row.get('Title', 'Untitled')}'...")

    # Call the incident preprocessing agent
    result = await incident_preprocess_agent.run(prompt, deps=deps)
    incident: AIIncident = result.output

    print(f"✓ [{idx + 1}/{len(SAMPLE_INCIDENTS)}] Structured incident {incident.incident_id}")
    return incident


# ============================================================================
# Main Workflow
# ============================================================================

async def main():
    """
    Main preprocessing workflow.

    Workflow:
    1. Iterate over sample incidents (or future CSV rows)
    2. Call preprocess_one_incident_row for each
    3. Ingest each structured incident into Neo4j
    4. Print summary statistics

    Note: This script is idempotent - you can re-run it safely.
    The Neo4j ingestion uses MERGE, so re-running won't duplicate nodes.
    """
    print("\n" + "=" * 70)
    print("AI INCIDENT DATABASE - PREPROCESSING")
    print("=" * 70)
    print()
    print("This script preprocesses AI incidents into structured AIIncident objects")
    print("and ingests them into Neo4j.")
    print()
    print("Prerequisites:")
    print("  ✓ OPENAI_API_KEY in .env file")
    print("  ✓ Neo4j running on localhost:7687")
    print()

    # Process all sample incidents
    print(f"Processing {len(SAMPLE_INCIDENTS)} sample incidents...\n")

    incidents = []
    for idx, row in enumerate(SAMPLE_INCIDENTS):
        try:
            incident = await preprocess_one_incident_row(row, idx)
            incidents.append(incident)
        except Exception as e:
            print(f"❌ Error processing incident {idx + 1}: {e}")
            import traceback
            traceback.print_exc()
            continue

    print()
    print("=" * 70)
    print("✓ INCIDENT PREPROCESSING COMPLETE")
    print("=" * 70)
    print()
    print(f"Summary:")
    print(f"  - Total incidents processed: {len(incidents)}")
    print()

    # Ingest to Neo4j
    print("Ingesting incidents to Neo4j...")
    for incident in incidents:
        try:
            ingest_incident(incident)
        except Exception as e:
            print(f"❌ Error ingesting {incident.incident_id}: {e}")
            import traceback
            traceback.print_exc()

    print()
    print("=" * 70)
    print("✓ INGESTION COMPLETE")
    print("=" * 70)
    print()
    print("Incidents have been ingested into Neo4j.")
    print("You can now query them or run risk assessments.")
    print()
    print("Example Cypher queries:")
    print("  - Count incidents:")
    print("    MATCH (i:Incident) RETURN count(i)")
    print()
    print("  - List all incidents:")
    print("    MATCH (i:Incident)")
    print("    RETURN i.incident_id, i.title, i.deployment_context")
    print()
    print("  - Find incidents by context:")
    print("    MATCH (i:Incident {deployment_context: 'transport'})")
    print("    RETURN i.incident_id, i.title")
    print()


if __name__ == "__main__":
    """
    How to use this script:

    1. Ensure prerequisites are met:
       - OPENAI_API_KEY in .env file
       - Neo4j running on localhost:7687 (or configured in .env)

    2. Run this script:
       python run_incident_preprocess_aiid.py

    The script will:
    - Process 3 sample incidents from the hardcoded SAMPLE_INCIDENTS list
    - Show text stats for each incident description
    - Structure each incident using an LLM agent
    - Ingest the structured incidents into Neo4j
    - Display a summary

    TO EXTEND WITH CSV LOADING:
    1. Add pandas import: import pandas as pd
    2. Replace SAMPLE_INCIDENTS with CSV loading:
       df = pd.read_csv("ai_incidents.csv")
       for idx, row in df.iterrows():
           incident = await preprocess_one_incident_row(row.to_dict(), idx)
           incidents.append(incident)
    """
    asyncio.run(main())
