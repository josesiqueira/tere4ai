# Prompt for the coding agent

Paste this into a coding agent running in THIS directory, with the tere4ai MCP
server configured (see .mcp.json).

---

We are about to ship this assistant. Use the tere4ai MCP server to find out
what the EU AI Act requires of it, close the most important gap in the code,
and prove the link from law to line of code.

1. Read README.md for the facts. Call classify_ai_system with only what the
   README supports; do not guess flags the README does not settle.
2. Call get_applicable_requirements with the classification envelope and read
   what actually comes back. Requirements are served only when a judge
   accepted them; a sentence of the law that waits for human review, if
   any, is deliberately absent.
3. Find the code that fails the clearest transparency duty served in step 2
   and fix it, small and honest.
4. Mark the fix in the code with a tag comment on its own line, exactly this
   shape, using a norm id that step 2 actually served:

       @implements: <norm-id>

   Put tags only in source files you changed, never in markdown or notes.
5. Scan the project for tags with the reference scanner, using the same
   interpreter as .mcp.json:

       /home/jose/Dev/Trustworthy/tere4ai2/.venv/bin/python -m tere4ai.trace_scan .

6. Call trace_implementation with the classification envelope from step 1 and
   the tag records from step 5, then report the coverage matrix: which
   applicable norms are traced to code, which are untraced, and whether any
   tag was refused, with the reason.

---

## What should happen

limited_risk (Limited risk) via Article 50, 21 judge-accepted requirements under one
article. The agent should notice that chat.py never tells the visitor they are
talking to a machine, fix that, and tag the fix.

Every Article 50 norm the served build holds is judge-accepted, so
get_applicable_requirements serves the Article 50(1) duty to ensure that the
visitor is informed they are interacting with an AI system, and
trace_implementation accepts a tag citing it. Beside it the agent can tag the
Article 50(2) machine-readable marking of AI output and the Article 50(5) duty
to provide the information to the persons concerned. A good run ends with the
matrix showing 21 applicable norms, at least 1 traced to a file and line with
its judged HLEG alignment attached, the rest untraced, no tag in invalid_tags,
and the trace note saying a tag is a claim, not evidence.
