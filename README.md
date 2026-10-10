<!-- edit docs/server/index.md, then run scripts/gen_server_docs.py -->
<!-- generated from docs/server/index.md: start -->
# TERE4AI

**The EU AI Act, as a knowledge graph your coding agent can call.**

TERE4AI is an open-source MCP server for teams building AI systems under
Regulation (EU) 2024/1689 as amended by Regulation (EU) 2026/1744 (the
Digital Omnibus), the AI Act in force. A coding agent describes the system it is
building and gets back a deterministic risk classification, engineering
requirements traced to byte-exact legal text, judged alignments to the AI
HLEG Trustworthy AI principles, and requirement-to-code traceability.
The rule ladder alone decides the level. A model's proposal is served only
after a check: an independent judge for norms, alignments, evidence and
backlog items, and for the elicitor's proposed facts a code check of their
quotes and the person who confirms them.

![Recorded MCP sessions, one per risk level, answers exactly as the server returned them](https://raw.githubusercontent.com/josesiqueira/tere4ai/main/docs/screenshots/readme-mcp-demo.png)

<!-- generated: notice -->
TERE4AI provides engineering and documentation support. It does not certify EU AI Act compliance and does not replace legal review, conformity assessment, or competent-authority interpretation.
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

Claude Code (`.mcp.json`), Claude Desktop, Cursor and other clients that
launch stdio MCP servers take this block; only the official MCP Python SDK
client is tested here.

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
```json
{
  "answer": {
    "risk_category": "high_risk",
    "unacceptable_risk": null,
    "annex_iii_category": "eu-ai-act:annex-iii:point-5",
    "rationale": [
      "rule high_risk: flag essential_services_access matches Annex III category 'essential private and public services' (eu-ai-act:annex-iii:point-5), high-risk under Article 6(2)",
      "status lowered to requires_human_review: unknown prohibition-relevant flags could change the outcome to Unacceptable risk"
    ],
    "fria": {
      "applicability": "unknown",
      "basis_nodes": [
        "eu-ai-act:article-27:paragraph-1"
      ]
    }
  },
  "status": "requires_human_review",
  "confidence": 0.5,
  "judge_verdict": "not_applicable_deterministic",
  "missing_facts": [
    "flags.subliminal_or_manipulative is unknown (prohibition-relevant, Article 5); absence is not treated as false",
    "flags.exploits_vulnerabilities is unknown (prohibition-relevant, Article 5); absence is not treated as false",
    "..."
  ],
  "source_nodes": [
    "eu-ai-act:annex-iii:point-5",
    "eu-ai-act:article-6:paragraph-2"
  ]
}
```
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
| Tool | What it does | Cost |
|---|---|---|
| `classify_ai_system` | Deterministic EU AI Act risk classification of a described AI system. | free |
| `coverage_report` | Structural coverage of the Act's graph and its judged layers, against the frozen source. | free |
| `elicit_features` | Propose the system_features facts of a plain-text system description, for the person to confirm before classify_ai_system runs. | paid |
| `evaluate_project_evidence` | Evaluate ONE untrusted project evidence artifact against ONE judge-accepted norm from the graph. | paid |
| `evaluate_project_evidence_batch` | Evaluate ONE untrusted evidence artifact against EVERY judge-accepted norm of one article, in a single envelope with per-norm results. | paid |
| `explain_requirement` | Explain one judged requirement (a normative statement) in depth. | free |
| `generate_control_backlog` | Generate a judged engineering control backlog from judge-accepted norms. | paid |
| `get_applicable_requirements` | Judge-accepted engineering requirements applicable to a classified system, grouped by source article. | free |
| `resolve_span` | The exact source text behind a span id, checked against the snapshot's checksum: snapshot file, sha256, start, end, and the text. | free |
| `source_trace` | Trace a graph node to its frozen source snapshot: file, sha256, span start/end, HTML anchor, and a text excerpt. | free |
| `trace_alignment` | Every EU-to-HLEG alignment for a norm or an HLEG requirement, with its judge verdict and evidence. | free |
| `trace_implementation` | Requirement-to-code traceability matrix for a classified system. | free |

12 tools: 8 free and 4 paid.
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
[the full explanation of the server](https://josesiqueira.github.io/tere4ai/).
<!-- generated from docs/server/index.md: end -->

## Documents

| File | Role |
|---|---|
| docs/architecture.md | Authoritative spec (layers, judges, milestones, traceability matrix) |
| docs/references.md | Reference register; all `@grounded_by` tags resolve here |
| docs/traceability.md | Generated by scripts/check_traceability.py, never hand-edited |
| AGENTS.md | Working rules for coding agents |
| USER.md | Domain guardrails and writing conventions |
| docs/DESIGN.md | Visual design system for the demo web UI |

## Layout

See docs/architecture.md Section 18. Key paths: `src/tere4ai/` (core),
`schema/json_schemas/` (machine-readable node and edge shapes),
`data/snapshots/` (frozen, checksummed legal sources), `data/graph_dumps/`
(versioned build artifacts), `web/` (thin read-only demo UI).

## Quick start (MILESTONE1, structural mirror)

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# build the Layer 0+1 graph dump from the frozen snapshot
.venv/bin/python -m tere4ai.parse_legal_structure

# run tests (acceptance: 113 articles, 180 recitals, 13 annexes)
.venv/bin/python -m pytest

# traceability gate (also generates docs/traceability.md)
.venv/bin/python scripts/check_traceability.py

# optional: load into Neo4j (set NEO4J_PASSWORD in .env first)
docker compose up -d
```

Note on graph dumps: `data/graph_dumps/` holds the published build
artifacts, tracked in git under CC BY 4.0 (see License). `layer1.json`
rebuilds deterministically with the parse_legal_structure command above (no
cost). `norms_core.json` and `alignments_core.json` come from the judged
Layer 2/3 pipeline, which makes paid model calls (architecture.md Section
6). Neo4j exports (`*.dump`, `*.nt`) are gitignored.

Serving a published build is an explicit act:
`.venv/bin/python scripts/activate_build.py <chain_id>` verifies the files
its publication manifest names and writes `ACTIVE_MANIFEST.json`. The MCP
server loads per call and follows it at once; the HTTP facade loads once at
startup, so a restart is the only way the facade changes builds. A file that
drifts from the activated publication refuses service. Without a pointer
both serve the three fixed dump files as before.

Each publication gets a build number, 1, 2, 3 in the order the publications
of one dump directory were recorded: publish prints `published Build N: <build id>, ...` and
activate prints `activated Build N (<build id>)`. The number is written into
`build_chain_<id>.json`, the frozen build record and `publications/<id>.json`;
commit the first and the last with the build, because `build_records/` is
git-ignored and the committed files keep a number from being issued twice.
If publish fails after the record is frozen (the terminal says `is published
as Build N`), `.venv/bin/python scripts/write_publication_manifest.py
<chain_id> --pointer` writes the missing publication manifest and pointer
from the chain record and the frozen record, with the same number; never
remove the chain record, since the same inputs would then be refused, not
renumbered. Until the evaluated graph is rebuilt from Layer 0, nothing is
published into `data/graph_dumps/`: a rehearsal publishes into a temporary
`--dump-dir`, since a number is never reused.

```bash

# demo web UI (thin, read-only; docs/DESIGN.md)
.venv/bin/python scripts/export_ui_data.py
cd web && npm install && npm run build && npx next start
```

## Demo flow (MILESTONE3)

The full demo flow (classify, requirements, evidence evaluation, backlog)
runs against the thin HTTP facade, which calls the same pure functions the
MCP server exposes. The UI never touches the database or model APIs
directly.

```bash
# 1. facade on port 8008 (loopback; CORS only for localhost:3111)
.venv/bin/uvicorn tere4ai.http_facade.app:app --port 8008

# 2. demo UI on port 3111, then open http://localhost:3111/assess
cd web && npm run build && npx next start -p 3111
```

/api/classify and /api/requirements are deterministic and free.
/api/evidence and /api/backlog perform PAID model calls (OpenAI generator
plus Anthropic runtime grounding judge; keys in .env, see .env.example), and
/api/elicit a PAID generator call (fact elicitation, no judge); all three
mark their responses with the X-TERE4AI-Paid-Call header. For the
dashboard's demonstration on pasted repositories (DEC-24), /api/backlog also
takes judge "on_demand": the generator alone, a backlog "not_checked" with a
record the facade signs (TERE4AI_ANSWER_SIGNING_KEY); /api/backlog/judge then
runs a demo judge of the generator's own family (TERE4AI_DEMO_JUDGE_MODEL,
gpt-6-sol) on that signed backlog, each a PAID call, every judged backlog
labelled "judged by <model>, the generator's own family (demo setting)". The
MCP tools and the inline mode keep DEC-07's independent judge.

## Build records, materialisation, publication and activation

Every build command (parse, extract, align, materialise, publish) writes an
execution record under `data/graph_dumps/build_records/` (DEC-16): what
ran, over which inputs (by digest), with which models and prompts, how far
it got (validated checkpoint keys against the expected total), how it
ended, and one outcome per gate. The facade serves them free on
`GET /api/builds` and `GET /api/builds/<record id or alias>`; the
dashboard's Build view reads only these routes. Every field says whether
it was recorded by the command, derived afterwards, or is unavailable.

Human decisions never edit a dump. Export the decisions file and its freeze
manifest from the dashboard, copy the manifest into `data/graph_dumps/`
(publication names its inputs by file under that directory), then:

    .venv/bin/python scripts/materialize_reference.py --pristine data/graph_dumps/norms_core.json \
        --decisions <decisions.json> --manifest <freeze-manifest.json>
    python -m tere4ai.align_hleg --norms data/graph_dumps/norms_core.reference.json
    .venv/bin/python scripts/publish_layer23.py --norms data/graph_dumps/norms_core.reference.json \
        --alignments data/graph_dumps/alignments_core.reference.json --manifest data/graph_dumps/<freeze-manifest.json>
    .venv/bin/python scripts/activate_build.py <chain id printed by publish>

Publish writes `build_chain_<id>.json` and `publications/<id>.json` only
after the post-load gates pass; `BUILD_CHAIN_CURRENT.txt` records the
latest publication and selects nothing; `NEO4J_TARGET.json` says whether
the database holds a validated build. Activation verifies the
publication's files and writes `ACTIVE_MANIFEST.json`; restart the facade
to serve it (the MCP server follows the pointer on its next call). Without
a pointer the facade serves the `*_core.json` files under their recomputed
chain, as before.

A run that stops (a usage limit, a crash) leaves its checkpoint; rerun
with `--resume` to continue it under a new run id that names the one it
resumes, after the inputs and configuration are checked; add
`--accept-legacy-checkpoint` (extract_norms only) for a checkpoint written
before build records existed; align_hleg always refuses checkpoint lines
without a run id. Starting the same output without `--resume` while a checkpoint
exists is refused. A provider overload is waited out: before each of five
pauses (10, 30, 90, 270 and 600 s, longer when the provider asks for it,
never above 600 s) the command prints one alert line on standard error;
when the sixth attempt fails it records the execution failed with "provider
unavailable after 6 attempts: <status or error>", keeps the checkpoint,
prints the command that resumes it and exits with code 3. A
declared parameter that the provider refuses stops the run the same way
with a configuration error and exit code 4: correct the row of
`config/model_parameters.json` and start again. A resume
under a changed row is refused, so when the checkpoint holds finished
units, move it away before starting again under the corrected row. A
published record is frozen: further work on the same alias continues as a
descendant record.

Tracked in git because they are publication evidence or inputs:
`build_chain_*.json`, `publications/`, `BUILD_CHAIN_CURRENT.txt`,
`*.reference.json`, `*.adjudicated.json`, the core dumps. Ignored because
they are per-checkout run state: `build_records/`, `*.checkpoint.jsonl`,
`*.writing.json`, `*.building.json`, `ACTIVE_MANIFEST.json`,
`NEO4J_TARGET.json`.

## Evaluation records (E1, E6)

Every measurement run writes one record under
`data/graph_dumps/evaluation_records/<record id>.json` with an immutable
copy of its outputs under `evaluation_records/<record id>/` (DEC-17).
The writers: `scripts/run_ablations.py` and `python -m tere4ai.eval.harness`
(E6 runs; `--no-record` to skip, `--dump-dir` to relocate, `--repeat-of
<record id>` to name the run this one repeats, refused with `--no-record`),
`scripts/variance_report.py`
(an E6 comparison naming the two runs it compared, by digest), and
`scripts/sample_judge_decisions.py` (E1 as three acts: the draw, which
refuses to overwrite any existing sheet without `--force` and binds the
sample to the activated publication or to the base build id; `--label
<decision id> <accept|reject> --by <name>` or `--label-file <csv> --by
<name>` (both in one act for distinct ids; an id named twice, by both or
by two rows, is refused with exit code 2), which record actor and time
per item and refuse (exit code 2) a
sheet whose bytes are not the bytes the last recorded draw or label act of
its sample wrote, so a `--no-record` label act breaks the chain for the
next one; `--compute`, which refuses a
label without an actor or a time and writes an analysis record with the
false accept and false reject rates per judge kind and pooled, a rate with
an empty denominator being null, never 0.0, and every rate a sample
estimate). `--dump-dir` is where `layer1.json`, `norms_core.json` and
`evaluation_records/` live, for the runner, the harness and the sampler
alike. The runner refuses (exit code 2) to resume a checkpoint that no
record names unless `--resume-unrecorded` is given, the note then recorded.
The runner refuses (exit code 2) to append to or rewrite a file whose bytes
are a pinned July 2026 summary or checkpoint, `--no-record` or not.
Without `--checkpoint` and `--summary` the runner writes both under
`eval/results/runs/<record id>/`, a fresh directory per run; a resume passes
`--checkpoint` explicitly, and a `--no-record` run must pass both.
A provider overload is waited out with five pauses and an alert line each;
when the sixth attempt fails the runner ends its record
partial with "provider unavailable after 6 attempts: <status or error>",
keeps the checkpoint, prints the command that resumes it and exits 3; the
unit in flight is run again on the resume, and a stop before any unit was
checkpointed starts a new record that names none. A failure no retry fixes
(a 401, a quota 429, any other 4xx, an SDK error before sending) ends the
record failed with "provider refused the request: <status or error> (item
<item id>)" and exits 5; the item is fixed before the next run, never
skipped. A refused declared parameter ends the record failed with the
configuration error and exits 4; an evaluation harness run
that meets one ends its record failed after that item and raises it. A
resume under another declaration (an edited row of
`config/model_parameters.json`) is refused and exits 2, naming
`model_parameters_sha256`: the runner compares the resumed record's
`models`, and every checkpointed unit's digest (a unit without one differs
too), with the loaded ones.
`scripts/elicit_benchmark_features.py` waits out an overload the same way
and, on a stop (exit 3) or a refusal naming the item (exit 5), keeps its
checkpoint and prints the command whose rerun resumes it; a refused
declared parameter exits 4. Its checkpoint entries and output name the
declaration (`models`), and a rerun over entries of another declaration is
refused (exit 2). It elicits over the build `load_active` serves,
and each entry also carries the quotes, the dropped facts and the prompt
record (version, template and rendered hashes, provisions, build); the
output names that prompt once beside `quotes_by_item` and
`dropped_by_item`, and a rerun over entries of another prompt version,
template or build is refused (exit 2) the same way.
The sampler's three acts on one sheet run one at a time: each holds the
lock file `<sheet>.lock` from its first read of the sheet to its record's
finish, and a second act waits (one line on stderr), then reads what the
first wrote. A `--sheet` or `--sheet-md` that is a symbolic link is
followed: the lock and every write go to the file it names. A label act
or `--compute` on a missing sheet is refused (exit code 2) before the
lock is taken.
The draw and the label act finish their record before the new bytes replace
the sheet: a copy or finish that fails leaves the sheet and its reading copy
as the act found them. `--compute` does the same for `error_rates.json`, so
its record keeps its own rates even when another sheet in the directory
computes at the same time. A refusal over sheet bytes no recorded act wrote
names the `cp` command that puts the last act's recorded copy in place;
labels typed into the sheet by hand are not kept by it (put them in a
`--label-file` CSV), and the reading copy is rewritten by the next label
act.
A draw over an active publication whose manifest lacks an input kind
refuses with a sentence and exit code 2 unless `--norms`, `--alignments`
or `--layer1` is given. The routes `GET /api/evaluations` (grouped by
build identity, newest first, records without a date last, the group with
no build identity last) and `GET /api/evaluations/<record id>` read the
records per request, the July 2026 measurements included as legacy
records synthesised from `eval/results/`,
`eval/gold/judge_label_sheet.json` and `docs/variance_study.md` (ids
derived from the file digests, dates only where an analysis file states
them, no build id for the ablation summaries because they carry none).
The July dates in the legacy records are pinned to the bytes of the July
files, never guessed. The contract with the dashboard is
`schema/json_schemas/evaluation_record.schema.json` and
`tests/fixtures/evaluation_records/`, regenerated by
`python -m tests.fixtures.evaluation_records.regenerate`.

A recording run of the runner writes a sidecar next to its checkpoint,
`<checkpoint>.record`, naming the record that owns the checkpoint. A resume
continues that record only when the store can read it and it names the same
checkpoint file; otherwise the runner refuses (exit code 2) and says why. A
checkpoint without a sidecar, a `--no-record` run's included, is resumed
only with `--resume-unrecorded`. The resuming record takes the sidecar over.
The sidecar is local state, git-ignored like the records: removing it makes
the checkpoint one no record names.

## Status

MILESTONE1 to MILESTONE3 implemented, MILESTONE4 harness ready (see docs/architecture.md Section 14
and docs/traceability.md, which is generated from code tags):

- MILESTONE1: deterministic Layer 1 mirror of the full Act in force, Regulation (EU)
  2024/1689 as amended by Regulation (EU) 2026/1744 (119 articles, 180
  recitals, 14 annexes, 521 points, 247 annex items), parsed from EUR-Lex's
  consolidated text and checked unit by unit against the Official Journal
  wording, each changed unit keeping its 2024 wording as an earlier version
  (DEC-23); crossrefs, coverage and trace tools, traceability gate.
- MILESTONE2: judged Layer 2/3 over the high-risk core: extracted norms and reified
  HLEG alignment assertions, each checked by an independent judge family
  (OpenAI generator, Anthropic judges), all in Neo4j with per-edge
  provenance and full audit logs. coverage_report serves the counts of the
  served build.
- MILESTONE3: runtime tools. Deterministic classify_ai_system (rules over real
  Article 5 and Annex III nodes, never an LLM) and
  get_applicable_requirements; judged evaluate_project_evidence and
  generate_control_backlog gated by the runtime grounding judge; every
  tool on the MCP server; HTTP facade plus the /assess demo flow,
  the recorded-session /mcp-demo page and the agent replay.
- MILESTONE4: evaluation harness with the six-condition ablation ladder, Section 12
  metrics, a 10-item seed gold set, and the located REF-15 benchmark. Live
  ablation runs and the full 60-80 item gold set are pending research work
  (cost-gated; see eval/README.md).

## Development

Optional, and only useful to the maintainer: this repository ships a pre-commit
hook that refuses a change to a DEC entry or the reference register unless the
maintainer's private research log records why the direction changed. Activate it
with:

    git config core.hooksPath hooks

Git cannot version that setting, so it is one command per clone. The hook itself
is versioned under `hooks/`. It detects that the private repository is absent and
does nothing, so it never blocks an outside contributor.

## License

Decided 2026-07-23 (OPEN-LICENSE resolved):

- Code (server, pipeline, web UI): AGPL-3.0-or-later, full text in
  [LICENSE](LICENSE).
- Graph metadata (the published dumps' structure, normative-statement
  metadata, alignments, provenance): CC BY 4.0, full text in
  [data/graph_dumps/LICENSE](data/graph_dumps/LICENSE). Attribution: Jose
  Antonio Siqueira de Cerqueira, TERE4AI.
- EU legal texts quoted inside the graph and dumps remain (c) European Union,
  reused under the EU legal-reuse framework (Commission Decision 2011/833/EU);
  no ownership is claimed over them and quotes are served byte-exact.
- ALTAI content is not redistributed pending its license check (task C2).
