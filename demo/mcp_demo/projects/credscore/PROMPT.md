# Prompt for the coding agent

Paste this into a coding agent running in THIS directory, with the tere4ai MCP
server configured (see .mcp.json).

---

This service is going into production and I need to know what the EU AI Act
requires of it before we plan the work.

Read README.md for the facts, then use the tere4ai MCP server: classify the
system with only the facts the README supports, fetch the applicable
requirements, and write COMPLIANCE.md in this directory. For each obligation
give the article, the norm id, its source span id, and the calibrated status
that came back. Group by article. At the end, list every fact you could not
settle from the README, and say plainly that nothing here is legal advice.

Do not implement anything yet. I want the obligations mapped first.

---

## What should happen

high_risk via Annex III point 5, and the Article 27 fundamental rights impact
assessment applies. 277 judge-accepted requirements across 23 articles, so the
right output is a mapped backlog rather than an afternoon of coding. This is the
tier where the tool changes the size of the project you thought you had.
