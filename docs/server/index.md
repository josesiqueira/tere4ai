<!-- readme: start -->
# TERE4AI

**The EU AI Act, as a knowledge graph your coding agent can call.**

TERE4AI is an open-source MCP server for teams building AI systems under
Regulation (EU) 2024/1689. A coding agent describes the system it is
building and gets back a deterministic risk classification, engineering
requirements traced to byte-exact legal text, judged alignments to the AI
HLEG Trustworthy AI principles, and requirement-to-code traceability.
The rule ladder alone decides the level. A model's proposal is served only
after a check: an independent judge for norms, alignments, evidence and
backlog items, and for the elicitor's proposed facts a code check of their
quotes and the person who confirms them.

![Recorded MCP sessions, one per risk level, answers exactly as the server returned them](https://raw.githubusercontent.com/josesiqueira/tere4ai/main/docs/screenshots/readme-mcp-demo.png)

<!-- generated: notice -->
<!-- end generated: notice -->

## Who it is for

- **Developers and their coding agents** shipping a system that falls under
  the Act: wire the MCP server in, ask what the law requires, tag the code
  that implements each requirement.
- **Requirements engineers and compliance leads** who need every generated
  requirement to cite the exact legal span it came from, and who need the
  server to say "unknown" when the facts are not there.
- **Researchers** studying evidence-gated generation over legal text: the
  judged graph, the provenance model and the evaluation harness are all here.

## Wire it into your agent

Clone, install, then add one config block. No database, no API keys: the
graph ships as versioned dumps in `data/graph_dumps/` and every free tool
reads them offline.

```bash
git clone https://github.com/josesiqueira/tere4ai.git && cd tere4ai
python3 -m venv .venv && .venv/bin/pip install -e .
```

```json
{
  "mcpServers": {
    "tere4ai": {
      "command": "/absolute/path/to/tere4ai/.venv/bin/python",
      "args": ["-m", "tere4ai.mcp_server.server"]
    }
  }
}
```

That block works as-is in Claude Code (`.mcp.json`), Claude Desktop, Cursor
and any other client that launches stdio MCP servers.

## What a call looks like

The agent describes the system as structured facts. Unknown is never
treated as false: a fact it does not state stays unknown, and the server
says so.

<!-- example request: start -->
```json
{
  "features": {
    "description": "CredScore evaluates the creditworthiness of natural persons applying for consumer loans and recommends a decision a loan officer can override.",
    "domain": "banking",
    "autonomy": "advisory",
    "flags": {
      "creditworthiness_evaluation": true,
      "profiling_of_natural_persons": true,
      "essential_services_access": true
    }
  }
}
```
<!-- example request: end -->

`classify_ai_system` answers as below, trimmed to the fields that matter.
Every answer also carries its source spans (the snapshot file, its
checksum, and the start and end of the span in code points), the id of the
graph build that answered, and the notice above.

<!-- generated: example -->
<!-- end generated: example -->

Supply the missing Article 5 facts and the same call settles to
`potentially_applicable`; `get_applicable_requirements` then returns the
judge-accepted norms for that level, grouped by article, each with its
source span.

## The tools

Every tool runs over stdio from the offline dumps. A free tool is
deterministic and calls no model; a paid tool makes model calls and says
so in its description (PAID) and in its annotations (openWorldHint).

<!-- generated: tools -->
<!-- end generated: tools -->

Paid tools need `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` in `.env` (see
`.env.example`). Without keys they return a `requires_human_review`
envelope that names the missing configuration; they never guess.

## What it is not

- Not a compliance certificate, a legal opinion or a conformity assessment.
- Not a model that "reads the law for you": classification is a fixed rule
  ladder over the real Article 5, Article 6 and Annex III nodes, and every
  model-produced norm or alignment passed an independent judge before it can
  be served. What the judges rejected or held for human review is published
  too (Review queue in the demo UI).
- Not a substitute for the facts: when a prohibition-relevant fact is
  unknown the status drops to `requires_human_review` and the answer names
  the fact.

How to read every answer, paid calls and the replay window, MCP revisions
and clients, and every tool's full description:
[the full explanation of the server](https://github.com/josesiqueira/tere4ai/blob/main/docs/server/index.md).
<!-- readme: end -->

## How to read every answer

<!-- reading: start -->
Every answer is one envelope with these fields:

<!-- generated: fields -->
<!-- end generated: fields -->

`status` is always one of these words, and no other:

<!-- generated: statuses -->
<!-- end generated: statuses -->

Rules for consuming agents:

- Treat `requires_human_review` as a stop: surface it to the human, do not
  proceed as if it were an approval.
- Never paraphrase a status upward (partially_satisfied is not satisfied).
- Fill `missing_facts` and re-ask instead of guessing.
- Cite `source_nodes` ids verbatim when relaying legal grounding.
<!-- reading: end -->

## Paid calls and the replay window

A paid tool is not charged twice for an identical call. A repeat with the
same caller, arguments, build and model settings inside
`TERE4AI_MCP_REPLAY_WINDOW_SECONDS` (default 600, measured on a monotonic
clock; 0 turns the replay off) gets the kept answer with a note in
`legal_status_notes` and its usage counts set to 0, since no model was
called; the first answer keeps its own counts. Refusals, degraded answers
and failures are never kept. The kept answers live in the memory of one
process (at most 256): two replicas behind a load balancer do not share
them, so a retry that lands on the other replica pays again.

## MCP revisions and clients

The server answers MCP revision 2026-07-28 (the stateless one, with the
version in each request) and legacy clients that start with an initialize
request (2025-11-25 and the earlier revisions the official MCP Python SDK
negotiates), from one process, over stdio and over streamable HTTP
(`TERE4AI_MCP_TRANSPORT=http`). It advertises no MCP logging capability and
answers `logging/setLevel` with method not found; diagnostics go to stderr.

Tested here: the official MCP Python SDK client (mcp 2.2), modes legacy
and 2026-07-28, over stdio and streamable HTTP
(`tests/unit/test_mcp_protocol_revisions.py`). No other client is tested.

As the vendors' public sources reported them on 2026-09-30 (read then, not
checked or tested here):

| Client | Reported status | Source |
|---|---|---|
| Claude Code, direct HTTP | Uses the v2 MCP client and 2026 negotiation by default | [release notes](https://github.com/anthropics/claude-code/releases) |
| Claude Code, stdio | No explicit Anthropic statement found about strict 2026-only stdio | none found |
| Claude Desktop | Modern support in some remote connector paths; one open report of 2026 body metadata with a 2025 HTTP header | [issue 93290](https://github.com/anthropics/claude-code/issues/93290) |
| OpenAI Codex CLI | 2026 support in code, behind the mcp_2026_07_28 feature | [features source](https://github.com/openai/codex/blob/main/codex-rs/features/src/lib.rs) |
| Codex CLI, stdio | Public request still open; experimental flag mentioned in a September comment | [issue 33952](https://github.com/openai/codex/issues/33952) |
| ChatGPT MCP Events | Requires MCP 2.0 / 2026-07-28 | [MCP Events](https://developers.openai.com/plugins/build/mcp-events) |
| ChatGPT tools-only connector | No primary page found stating its revision | none found |
| Cursor | Speaks 2025-11-25 and earlier; no timeline for 2026 (staff, 21 and 25 September) | [forum thread](https://forum.cursor.com/t/mcp-client-cannot-connect-to-modern-only-2026-07-28-streamable-http-servers-legacy-initialize-rejected/172536) |
| VS Code / GitHub Copilot | Source still sets `LATEST_PROTOCOL_VERSION = "2025-11-25"` | [source](https://github.com/microsoft/vscode/blob/main/extensions/copilot/src/extension/common/modelContextProtocol.ts) |
| Windsurf | No primary source found for its supported revision | none found |
| MCP Inspector | Inspector v2 supports legacy and modern negotiation | [docs](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/docs/2026-07-28/tools/inspector.mdx) |

This is why legacy support stays: Cursor and VS Code are reported to speak
only the earlier revisions.

## Span offsets

In a source span, `start` and `end` count Unicode code points in the
snapshot file decoded as UTF-8, not bytes, and the checksum
(`snapshot_sha256`) is over the file's bytes. Slicing the decoded text at
`start` and `end` gives the span's exact text; slicing the raw bytes at the
same numbers gives other text wherever a character before the span takes
more than one byte. resolve_span and source_trace answer with the same
offsets and checksum.

## Duplicate keys

JSON leaves a repeated key inside one object to the receiver (RFC 8259,
Section 4). This server reads the last of the repeated keys and refuses
nothing, over MCP (stdio, the tool arguments) and on the HTTP facade (the
request body of POST /api/classify): an arguments object that names
`features` twice, first an email spam filter and then a system that ranks
job applicants, is classified as the second, high risk, on both surfaces
(`tests/unit/test_duplicate_keys.py`). Send each key once.

## The instructions the server sends

A client receives this text when it connects:

<!-- generated: instructions -->
<!-- end generated: instructions -->

## The tool reference

Every tool's whole served description, its annotations and its input
fields: [the tool reference](tools.md).
