# Demo Revamp Plan C: Centerpiece Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the demo centerpiece: structural honesty guards, example presets with fact-panel provenance, the elicit mode, the evidence subgraph, the requirements board, the agent replay page, and the venue-neutral demo script.

**Architecture:** Builds on merged Plans A and B. Task 1 makes the honesty guards structural before any new surface ships (web-copy scan gate, real chain id served through export_ui_data.py, shared facade module). UI tasks follow the established inline-component convention; the only new npm dependency is d3-force for the subgraph. Spec: docs/superpowers/specs/2026-07-29-demo-revamp-design.md, including the recorded deviation: NO per-fact quote affordance until the elicitor schema extension (increment 2).

**Tech Stack:** Python 3.12 + pytest (guards, export script), Next.js App Router + TypeScript + Tailwind v4, d3-force, Lucide.

## Global Constraints

- NEVER use em dashes anywhere; never use en dashes as a sentence break.
- Banned claim terms (compliant, certified, legally approved) never in UI-generated copy; Task 1's gate enforces this mechanically from then on.
- UI tasks: invoke `impeccable:impeccable` via the Skill tool BEFORE writing TSX; docs/DESIGN.md governs; components inline in page files unless a task names a component file.
- Thin read-only consumer: UI fetches only facade routes and public/ assets; use FACADE_URL from web/src/lib/facade.ts (created in Task 1) everywhere.
- Calibrated-vocabulary discipline: the requirements board and every status render uses the vocabulary terms verbatim with plain-language subtitles; never "fulfilled", never checkmark-equals-compliant iconography.
- Inherited contracts from Plan B's final review: remove the /agent "soon" badge only when the page ships (Task 6); no per-fact quote affordance anywhere (increment 2); the replay page masks NOTHING when rendering recorded envelopes.
- Verification: `cd web && npx tsc --noEmit && npm run build`; Python `.venv/bin/python -m pytest -q` (baseline 571 passed, 11 skipped), ruff, `scripts/check_traceability.py`, `scripts/check_release_hygiene.py`. Never `uv run pytest`. Never commit uv.lock.
- graphify rule: run `graphify query "<question>"` from /home/jose/Dev/Trustworthy before exploring beyond named files; include this in subagent prompts.

---

### Task 1: Structural honesty guards, served chain id, shared facade module

**Files:**
- Create: `tests/unit/test_web_copy_honesty.py`
- Modify: `scripts/export_ui_data.py` (chain id + schema flags into ui_data.json)
- Modify: `web/public/ui_data.json` (regenerated, never hand-edited)
- Modify: `web/src/app/page.tsx` (display the served chain id verbatim, drop the client-side digest)
- Create: `web/src/lib/facade.ts`
- Modify: `web/src/app/assess/page.tsx`, `web/src/app/how-it-works/page.tsx` (import FACADE_URL from the lib)

**Interfaces:**
- Consumes: `schema_flag_names()` from `tere4ai.elicit_features.elicitor` (Plan A); `data/graph_dumps/BUILD_CHAIN_CURRENT.txt` (12-hex id) and `data/graph_dumps/build_chain_<id>.json`.
- Produces: `ui_data.build.chain_id` (string, verbatim from BUILD_CHAIN_CURRENT.txt), `ui_data.schema_flags` (sorted list of the 34 flag names); `web/src/lib/facade.ts` exporting `export const FACADE_URL = "http://localhost:8008";`. Tasks 2 to 6 rely on all three.

- [ ] **Step 1: Write the failing guard tests**

```python
"""Structural honesty guards for the demo web UI.

The server side has a scoped banned-term contract (DEC-08) and a dash
gate; until this file existed, nothing scanned the UI's own copy. These
guards walk web/src so a hand-typed em dash or claim term can never ship.
Word-boundary matching keeps the mandated caveat legal ("certify",
"compliance" are not the banned claim terms).
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
WEB_SRC = ROOT / "web" / "src"
BANNED = re.compile(r"\b(compliant|certified|legally approved)\b", re.IGNORECASE)
DASHES = re.compile("[\u2014\u2013]")  # em dash, en dash, as escapes (see tests/unit/test_web_copy_honesty.py)


def _web_files():
    files = [
        p for p in WEB_SRC.rglob("*")
        if p.suffix in {".tsx", ".ts", ".css"} and p.is_file()
    ]
    assert files, "web/src scan found no files; layout changed?"
    return files


def test_web_copy_has_no_em_or_en_dashes():
    offenders = [
        str(p.relative_to(ROOT))
        for p in _web_files()
        if DASHES.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_web_copy_has_no_banned_claim_terms():
    offenders = []
    for p in _web_files():
        for m in BANNED.finditer(p.read_text(encoding="utf-8")):
            offenders.append(f"{p.relative_to(ROOT)}: {m.group(0)}")
    assert offenders == []


def test_ui_data_serves_the_recorded_chain_id_and_schema_flags():
    ui = json.loads((ROOT / "web" / "public" / "ui_data.json").read_text())
    current = (
        (ROOT / "data" / "graph_dumps" / "BUILD_CHAIN_CURRENT.txt")
        .read_text()
        .strip()
    )
    assert ui["build"]["chain_id"] == current
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from tere4ai.elicit_features.elicitor import schema_flag_names

    assert ui["schema_flags"] == schema_flag_names()


def test_presets_cover_every_schema_flag():
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from tere4ai.elicit_features.elicitor import schema_flag_names

    presets_text = (WEB_SRC / "app" / "assess" / "presets.ts").read_text()
    missing = [f for f in schema_flag_names() if f'"{f}"' not in presets_text]
    assert missing == [], f"presets.ts missing schema flags: {missing}"
```

Run: `.venv/bin/python -m pytest tests/unit/test_web_copy_honesty.py -v`
Expected: the two scan tests PASS (Plan B left web/src clean); the chain-id test FAILS (ui_data.json has no chain_id yet); the presets test FAILS (presets.ts lists 22 of 34 flags). Both failures are the point; the presets one stays red until Task 2 and that is acceptable ONLY within this branch: note it in the commit message.

- [ ] **Step 2: Extend export_ui_data.py**

After the existing payload assembly, before writing OUT_PATH, add (imports at the top with the existing ones):

```python
from tere4ai.elicit_features.elicitor import schema_flag_names

CHAIN_CURRENT = ROOT / "data" / "graph_dumps" / "BUILD_CHAIN_CURRENT.txt"
```

and in the payload construction:

```python
    payload["build"]["chain_id"] = CHAIN_CURRENT.read_text().strip()
    payload["schema_flags"] = schema_flag_names()
```

Adapt variable names to the script's actual payload dict. Then regenerate: `.venv/bin/python scripts/export_ui_data.py` and confirm `git diff web/public/ui_data.json` shows only the two additions.

- [ ] **Step 3: Serve the chain id on the coverage page**

In web/src/app/page.tsx: extend the build type with `chain_id: string`; replace the client-computed source-set digest and its footnote sentence with the served value: `publication chain <chain_id>, recorded by the build and verified at server startup`. Delete the crypto import and digest computation entirely. Keep the snapshot count sentence and the HLEG caveat sentence.

- [ ] **Step 4: Create web/src/lib/facade.ts and deduplicate**

```ts
/* Single source of the facade origin for every page. */
export const FACADE_URL = "http://localhost:8008";
```

Replace the module-local constants in assess/page.tsx and how-it-works/page.tsx with `import { FACADE_URL } from "@/lib/facade";` (verify the @/ alias exists in tsconfig; use a relative import if not).

- [ ] **Step 5: Verify**

`.venv/bin/python -m pytest tests/unit/test_web_copy_honesty.py -v` (3 pass, presets test still red, expected); `cd web && npx tsc --noEmit && npm run build` clean; `.venv/bin/python -m ruff check src scripts tests` clean.

- [ ] **Step 6: Commit**

```bash
git add tests/unit/test_web_copy_honesty.py scripts/export_ui_data.py web/public/ui_data.json web/src/app/page.tsx web/src/lib/facade.ts web/src/app/assess/page.tsx web/src/app/how-it-works/page.tsx
git commit -m "Demo revamp C1: web-copy honesty gate, served chain id, shared facade module (presets flag test red until C2)"
```

---

### Task 2: Example presets and schema-complete flag panel

**Files:**
- Modify: `web/src/app/assess/presets.ts`
- Modify: `web/src/app/assess/page.tsx` (only if the flag panel derives its rows from ALL_FLAG_KEYS and needs the new keys grouped)

**Interfaces:**
- Consumes: the 34 schema flags (Task 1 serves them in ui_data.schema_flags; presets.ts stays a static module and lists them literally, with the drift gate from Task 1 enforcing completeness).
- Produces: `SCENARIO_PRESETS` with exactly five presets, ids: `spamguard`, `shopbot`, `credscore`, `moodwatch`, `moodwatch-safety`. Task 7's demo script references these ids.

- [ ] **Step 1: Invoke the impeccable skill**, then update ALL_FLAG_KEYS in presets.ts to all 34 schema flag names (sorted as in the schema; the Task 1 gate defines done).

- [ ] **Step 2: Replace the three existing presets with the five example presets.** Source of truth for facts: the examples' READMEs and SpamGuard's recorded request fixture (tests/fixtures/demo_sessions/spamguard-classify.jsonl carries the exact 34-flag FEATURES that produced the archived confident-minimal envelope; reuse those values verbatim for the spamguard preset). For the other four, derive flags honestly from /home/jose/Dev/Trustworthy/examples/*/README.md descriptions:
  - shopbot: interacts_with_natural_persons true, generates_synthetic_content true, everything prohibition/Annex III false. Hint: transparency_only.
  - credscore: creditworthiness_evaluation true, essential_services_access true, profiling_of_natural_persons true, prohibitions false. Hint: high_risk, FRIA applies (the FRIA outcome needs the deployer facts; see Step 3).
  - moodwatch: emotion_recognition true, emotion_recognition_workplace_or_education true, emotion_recognition_medical_or_safety false, causes-harm family per the README. Hint: prohibited.
  - moodwatch-safety: same as moodwatch but emotion_recognition_medical_or_safety "unknown" with a description claiming a driver-fatigue safety purpose. Hint: requires_human_review (the calibration beat; this preset deliberately leaves the exception fact unsettled).
  Each preset's description comes from its example README's "Product description" section, condensed to a few sentences, no em dashes.

- [ ] **Step 3: Deployer facts.** Check whether assess/page.tsx's form models the two deployer booleans (deployer.body_governed_by_public_law, private_entity_providing_public_services). If yes, extend ScenarioPreset with them and set credscore's honestly (private entity providing an essential private service, per its README). If the form does NOT model them, do NOT add form fields in this task; record in your report that credscore's FRIA block will honestly return unknown pending deployer facts, and leave the preset without them. Either outcome is acceptable; silence is not.

- [ ] **Step 4: Verify**: `.venv/bin/python -m pytest tests/unit/test_web_copy_honesty.py -v` now fully green (4 of 4, presets gate satisfied); `cd web && npx tsc --noEmit && npm run build` clean.

- [ ] **Step 5: Commit**

```bash
git add web/src/app/assess/presets.ts web/src/app/assess/page.tsx
git commit -m "Demo revamp C2: five example presets, schema-complete flag panel"
```

---

### Task 3: Elicit mode on the assess page

**Files:**
- Modify: `web/src/app/assess/page.tsx`

**Interfaces:**
- Consumes: `POST ${FACADE_URL}/api/elicit` with `{"description": string}` (min 30 chars server-side): 200 with a Section 8 envelope whose `answer` is `{features, notes}` or null; 503 `{error}` without model keys; 422 on short input. Envelope `missing_facts` lists un-elicited flags as `flag not elicited: <name>`.
- Produces: fact-panel provenance marking that Task 7's demo script narrates.

- [ ] **Step 1: Invoke the impeccable skill.** Then add an "Elicit facts from description" button beside the existing description textarea, gated on description length >= 30 with a visible character hint.

- [ ] **Step 2: Wire the call.** On click: POST to /api/elicit; while pending, disable with a spinner (DESIGN.md Spinner recipe). On 200 with features: fill domain/autonomy/flags from `answer.features` (tri-state mapping: present true/false as "true"/"false"; absent flags stay "unknown"), mark every filled control as elicited (a small amber-tinted "elicited" chip using existing badge classes next to each affected control, cleared for a control the user subsequently edits), and render `answer.notes` plus the envelope's status badge and confidence in a dismissible panel above the form. On 200 with null features (elicitation failed): show the envelope's missing_facts and notes in the same panel, fill nothing. On 503/422/network error: show the error in the panel, degraded, never empty. NO per-fact quote affordance (recorded spec deviation; the notes panel is the only provenance surface until increment 2).

- [ ] **Step 3: Honesty copy.** The panel carries one fixed sentence: "Elicited facts are proposals: confirm or edit them, the deterministic ladder alone decides." (exact text).

- [ ] **Step 4: Verify**: `cd web && npx tsc --noEmit && npm run build` clean; `.venv/bin/python -m pytest tests/unit/test_web_copy_honesty.py -q` green.

- [ ] **Step 5: Commit**

```bash
git add web/src/app/assess/page.tsx
git commit -m "Demo revamp C3: elicit mode fills the fact panel as marked, editable proposals"
```

---

### Task 4: Evidence subgraph component

**Files:**
- Modify: `web/package.json` (+ d3-force, dev + @types/d3-force)
- Create: `web/src/app/assess/evidence-graph.tsx`
- Modify: `web/src/app/assess/page.tsx` (render beside classification and requirement groups)

**Interfaces:**
- Consumes: `envelope.graph_evidence_subgraph` as served today. FIRST read its real shape from the fixture (tests/fixtures/demo_sessions/spamguard-classify.jsonl envelope field) and from a requirements envelope (run the free classify + requirements against the dump in a scratch script if needed); the component's types mirror the REAL shape, whatever it is; if the subgraph is empty in a given envelope, render nothing.
- Produces: `<EvidenceGraph subgraph={...} />` client component; click on a node with a span/source id opens a side panel fetching `${FACADE_URL}/api/span/<id>` for verbatim text (that route exists; confirm its response shape before coding the panel).

- [ ] **Step 1: Install the dependency**: `cd web && npm install d3-force && npm install -D @types/d3-force` (lockfile committed with the task).

- [ ] **Step 2: Invoke the impeccable skill**, then build the component: a client component running d3-force's simulation (forceLink, forceManyBody, forceCenter) over the subgraph's nodes/edges into a static-after-settle SVG (run the simulation synchronously with `simulation.tick()` in a loop, no animation loop needed); nodes colored by layer using the chart tokens (chart-1 through chart-5 for layers 0 to 4 or whatever layer key the real shape carries); node labels truncated with title tooltips; edges as lines with muted stroke. Height ~320px, `overflow-x-auto` container, dark-mode correct by using tokens only.

- [ ] **Step 3: Wire it into assess/page.tsx** beside the classification result card and each requirements article group that carries a non-empty subgraph, behind a small "show evidence graph" toggle so the accordion stays scannable.

- [ ] **Step 4: Verify**: `cd web && npx tsc --noEmit && npm run build` clean; honesty gate green.

- [ ] **Step 5: Commit**

```bash
git add web/package.json web/package-lock.json web/src/app/assess/evidence-graph.tsx web/src/app/assess/page.tsx
git commit -m "Demo revamp C4: interactive evidence subgraph rendered from envelope data"
```

---

### Task 5: Requirements board

**Files:**
- Create: `web/src/lib/vocab.ts` (move VOCAB_SUBTITLES from how-it-works, export shared)
- Modify: `web/src/app/how-it-works/page.tsx` (import from the lib)
- Modify: `web/src/app/assess/page.tsx` (the board)

**Interfaces:**
- Consumes: the requirements envelope already loaded by the page; evidence-evaluation envelopes produced in-page (the page already has an evidence flow) whose `status` is one of the calibrated vocabulary values, keyed by norm id.
- Produces: a board section grouping every served requirement into five columns by status: requirements with no evidence evaluation sit in `applicable_missing_evidence` (the to-be-done column); each evaluated requirement moves to its envelope's status column. Column headers: the vocabulary term verbatim (mono, small) with the shared subtitle under it. Counts per column. No other wording.

- [ ] **Step 1: Invoke the impeccable skill.** Extract VOCAB_SUBTITLES to web/src/lib/vocab.ts verbatim; update the how-it-works import; tsc must stay clean.

- [ ] **Step 2: Build the board** as an inline component in assess/page.tsx fed by a `Map<normId, status>` derived from the page's existing evidence-result state (verify the real state shape first). Five columns on lg, stacked on mobile; a requirement card in a column shows the article group, the norm id (mono, truncated), and its status badge using the page's existing badge pattern. The board renders under the requirements accordion, only when requirements are loaded.

- [ ] **Step 3: Honesty guard in copy**: the board's section heading is "Requirements by evidence status"; the empty-board hint is "No evidence evaluated yet: every applicable requirement is waiting for evidence." No checkmarks anywhere; the satisfied_with_evidence column uses the same neutral badge style as the rest.

- [ ] **Step 4: Verify**: `cd web && npx tsc --noEmit && npm run build`; honesty gate green.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/vocab.ts web/src/app/how-it-works/page.tsx web/src/app/assess/page.tsx
git commit -m "Demo revamp C5: requirements board grouped by calibrated evidence status"
```

---

### Task 6: Agent replay page

**Files:**
- Create: `web/src/app/agent/page.tsx`
- Modify: `web/src/app/nav-links.tsx` (remove the "soon" badge from the Agent item)

**Interfaces:**
- Consumes: `GET ${FACADE_URL}/api/demo/sessions` -> `{"sessions": [name]}` or 404 when disabled; `GET ${FACADE_URL}/api/demo/sessions/<name>` -> raw JSONL, lines `{seq, ts, tool, request, envelope, repo_ref}`.
- Produces: the /agent route; the sidebar badge removal completes Plan B's recorded contract.

- [ ] **Step 1: Invoke the impeccable skill**, then build the page: a session picker (list from the endpoint; 404 renders a setup hint naming TERE4AI_DEMO_SESSIONS_DIR and the examples sessions folder, degraded not empty); on selection, parse the JSONL and show a step-through: previous/next controls, "exchange N of M", each step a split view: left, the raw request and envelope pretty-printed JSON in `font-mono text-xs` scrollable panes with copy buttons; right, a rendered summary: the tool name, the envelope's status badge, confidence, judge verdict, missing_facts, and a per-tool one-liner (classify: risk_category and FRIA applicability; requirements: article-group count; evidence: the calibrated status; other tools: the answer's top-level keys). Render values EXACTLY as recorded; mask or rewrite nothing.

- [ ] **Step 2: Remove the `soon: true` from the Agent item in nav-links.tsx** and delete the badge-rendering branch if no other item uses it.

- [ ] **Step 3: Verify**: `cd web && npx tsc --noEmit && npm run build` (route list now includes /agent); honesty gate green. Manual sanity if the facade is running with TERE4AI_DEMO_SESSIONS_DIR pointed at the SpamGuard sessions dir: the recorded exchange renders. If the facade is not running in your environment, say so in the report; do not fake a screenshot.

- [ ] **Step 4: Commit**

```bash
git add web/src/app/agent/page.tsx web/src/app/nav-links.tsx
git commit -m "Demo revamp C6: agent session replay page, raw exchange beside rendered meaning"
```

---

### Task 7: Venue-neutral demo script, screenshots, final gates

**Files:**
- Modify: `docs/DEMO.md` (full rewrite)
- Create: `docs/screenshots/` additions (best effort, see Step 2)

**Interfaces:** consumes everything shipped in C1 to C6 plus the preset ids from Task 2.

- [ ] **Step 1: Rewrite docs/DEMO.md venue-neutral** with exactly these sections: Setup (docker compose profile demo, or dev mode: uvicorn facade on 8008 plus next dev, TERE4AI_DEMO_SESSIONS_DIR pointing at the examples sessions dir, keys optional); The 7-minute talk (coverage tiles and chain id, one click through the five presets in ascending severity ending on moodwatch prohibited and moodwatch-safety abstaining, evidence subgraph on credscore, close on the agent replay page); The 20-minute panel cut (adds: How it works diagrams, judge drill-down pointers to docs/live_audit_log.md and the review queue, the requirements board with a live paid evidence call if keys present, elicit mode on an audience-supplied description); Live agent mode (checklist: keys, MCP config snippet for a coding agent pointing at the stdio server, the examples stage-0 protocol, curated-repo placeholder for increment 2); Fallback matrix (every live step names its replay or screenshot fallback). No REFSQ mention anywhere; no em dashes; reference preset ids exactly as Task 2 defined them.

- [ ] **Step 2: Screenshots, best effort.** If the environment allows running the facade (`.venv/bin/python -m uvicorn tere4ai.http_facade.app:create_app --factory --port 8008` or the repo's documented command; check docs or docker-compose for the exact form) and `cd web && npm run dev`, capture: coverage with tiles, assess with a preset classified, the subgraph open, the board, the agent replay, how-it-works; save as docs/screenshots/demo-<page>.png. Use the playwright browser tools if available in your environment. If the stack cannot run, write the fallback note in your report and leave existing screenshots untouched; do NOT fabricate or edit images.

- [ ] **Step 3: Full gates**: `cd web && npx tsc --noEmit && npm run build && cd ..`; `.venv/bin/python -m pytest -q` (expect 575+ passed, 11 skipped); ruff; traceability (commit docs/traceability.md if regenerated); release hygiene.

- [ ] **Step 4: Commit and push**

```bash
git add docs/DEMO.md docs/screenshots docs/traceability.md
git commit -m "Demo revamp C7: venue-neutral demo script with fallback matrix and fresh screenshots"
git push -u origin demo-revamp-c
```
