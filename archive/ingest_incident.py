"""
Deterministic Neo4j Ingestion for AI Incidents

This module provides functions to write AIIncident objects to Neo4j.

Key principles:
  - Deterministic: same incident → same Neo4j nodes
  - No LLM calls: pure Cypher execution
  - Idempotent: uses MERGE, safe to run multiple times
  - Clean separation: LLM extraction happens elsewhere (agent_incident_preprocess.py)

Schema:
  (i:Incident {
      incident_id,
      source_db,
      source_id,
      source_url,
      title,
      description,
      date,
      alleged_deployer,
      alleged_developer,
      alleged_harmed_parties,
      implicated_systems,
      system_function,
      deployment_context,
      affected_individuals,
      harms_observed
  })

Future extensions may add relationships:
  - (Incident)-[:ASSESSED_BY]->(RiskAssessment)
  - (Incident)-[:INVOLVES]->(Actor)
  - (Incident)-[:RELATES_TO]->(Article)
"""

from typing import Optional
from models.incidents import AIIncident
from config.neo4j_config import get_neo4j_driver


def ingest_incident(incident: AIIncident) -> None:
    """
    Deterministically write an AIIncident to Neo4j.

    Creates or updates an Incident node with all fields from the AIIncident model.
    Uses MERGE for idempotency - safe to run multiple times.

    Args:
        incident: AIIncident object to ingest

    Schema:
        (i:Incident {
            incident_id,
            source_db,
            source_id,
            source_url,
            title,
            description,
            date,
            alleged_deployer,
            alleged_developer,
            alleged_harmed_parties,
            implicated_systems,
            system_function,
            deployment_context,
            affected_individuals,
            harms_observed
        })

    Example:
        >>> from models.incidents import AIIncident, SourceInfo
        >>> incident = AIIncident(
        ...     incident_id="incident_0001",
        ...     source=SourceInfo(source_db="AIID", source_id="1", source_url=None),
        ...     title="Test Incident",
        ...     description="Test description",
        ... )
        >>> ingest_incident(incident)
        ✓ Ingested incident incident_0001 into Neo4j
    """
    # Cypher query to create/update Incident node
    # MERGE ensures idempotency - running multiple times won't create duplicates
    cypher = """
    MERGE (i:Incident {incident_id: $incident_id})
    SET i.source_db = $source_db,
        i.source_id = $source_id,
        i.source_url = $source_url,
        i.title = $title,
        i.description = $description,
        i.date = $date,
        i.alleged_deployer = $alleged_deployer,
        i.alleged_developer = $alleged_developer,
        i.alleged_harmed_parties = $alleged_harmed_parties,
        i.implicated_systems = $implicated_systems,
        i.system_function = $system_function,
        i.deployment_context = $deployment_context,
        i.affected_individuals = $affected_individuals,
        i.harms_observed = $harms_observed
    """

    # Build parameters dictionary from AIIncident
    # Convert HttpUrl to string, handle None values
    params = {
        "incident_id": incident.incident_id,
        "source_db": incident.source.source_db,
        "source_id": incident.source.source_id,
        "source_url": str(incident.source.source_url) if incident.source.source_url else None,
        "title": incident.title,
        "description": incident.description,
        "date": incident.date,
        "alleged_deployer": incident.alleged_deployer,
        "alleged_developer": incident.alleged_developer,
        "alleged_harmed_parties": incident.alleged_harmed_parties,
        "implicated_systems": incident.implicated_systems,
        "system_function": incident.system_function,
        "deployment_context": incident.deployment_context,
        "affected_individuals": incident.affected_individuals,
        "harms_observed": incident.harms_observed,
    }

    # Execute deterministic Neo4j write
    with get_neo4j_driver() as driver:
        driver.execute_query(cypher, **params)

    print(f"✓ Ingested incident {incident.incident_id} into Neo4j")
