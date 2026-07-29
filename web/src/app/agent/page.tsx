"use client";

/* Agent session replay (Task 6, docs/superpowers/specs/2026-07-29-demo-revamp-design.md
   "Agent" page). Recorded MCP exchanges from real example development
   (examples/<n>/artifacts/sessions/<date>-<label>.jsonl), served read-only
   by the facade's GET /api/demo/sessions and /api/demo/sessions/<name>
   (docs/architecture.md Section 9, Phase 1 demo UI). Split view per
   exchange: the raw request and envelope JSON on the left, exactly as
   recorded (font-mono, scrollable, copy buttons), and a rendered summary
   on the right (tool, status, confidence, judge verdict, missing facts, a
   short per-tool one-liner). Absolute replay honesty: nothing here masks,
   rewrites, or reformats a recorded value beyond pretty-printing; the raw
   pane is the ground truth and the rendered pane only summarizes it.
   Enabled only when the facade's TERE4AI_DEMO_SESSIONS_DIR is set; when it
   is not, the page renders a setup hint naming the env var and an example
   sessions folder, never an empty page (Section 13, no silent
   degradation). */

import { useEffect, useState } from "react";
import { AlertCircle, Check, ChevronLeft, ChevronRight, Copy, Loader2 } from "lucide-react";

import { FACADE_URL } from "@/lib/facade";

/* A recorded envelope is read as loosely as the raw session file itself:
   every field is optional at the type level and re-checked with typeof at
   render time, so a page bug can never invent a value that was not
   actually recorded. */
type SessionEnvelope = Record<string, unknown>;

type SessionLine = {
  seq: number;
  ts: string;
  tool: string;
  request: unknown;
  envelope: SessionEnvelope;
  repo_ref: unknown;
};

type ListState =
  | { kind: "loading" }
  | { kind: "disabled"; message: string }
  | { kind: "error"; message: string }
  | { kind: "ready"; sessions: string[] };

type SessionState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; lines: SessionLine[] };

const EXAMPLE_SESSIONS_DIR = "examples/1-minimalrisk-spamguard/artifacts/sessions";
const SESSIONS_ENV_VAR = "TERE4AI_DEMO_SESSIONS_DIR";

const BUTTON_OUTLINE_SM =
  "inline-flex items-center justify-center h-8 px-3 rounded-md border " +
  "border-input bg-transparent shadow-xs text-xs font-medium " +
  "transition-all duration-200 hover:bg-accent disabled:pointer-events-none " +
  "disabled:opacity-50";
const ICON_BUTTON_SM =
  "inline-flex items-center justify-center h-8 w-8 rounded-md border " +
  "border-input bg-transparent shadow-xs transition-all duration-200 " +
  "hover:bg-accent disabled:pointer-events-none disabled:opacity-50";

/* Same closed-vocabulary badge convention as web/src/app/assess/page.tsx
   (DEC-08): green only for satisfied_with_evidence, red only for
   rejected_as_unsupported, muted for every other status. An unrecognized
   status (a recorded envelope from a future schema version) falls back to
   the muted style rather than guessing. */
function StatusBadge({ status }: { status: string }) {
  const green = status === "satisfied_with_evidence";
  const red = status === "rejected_as_unsupported";
  const cls = green
    ? "text-green-600 dark:text-green-400 border-green-600/40"
    : red
      ? "text-destructive border-destructive/40"
      : "text-muted-foreground border-border";
  return (
    <span className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${cls}`}>
      {status}
    </span>
  );
}

function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard can be unavailable (permissions, non-secure context); the
      // pane's own text is still selectable and copyable by hand.
    }
  }
  return (
    <button
      type="button"
      className={`${BUTTON_OUTLINE_SM} gap-1.5`}
      onClick={() => void copy()}
      aria-label={`Copy the ${label} JSON`}
    >
      {copied ? (
        <Check className="h-3.5 w-3.5" aria-hidden="true" />
      ) : (
        <Copy className="h-3.5 w-3.5" aria-hidden="true" />
      )}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

/* Pretty-printed only: JSON.stringify with indentation changes whitespace,
   never a value. This is the raw pane; it is the honesty ground truth for
   the exchange. */
function JsonPane({ title, value }: { title: string; value: unknown }) {
  const text = JSON.stringify(value, null, 2);
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {title}
        </p>
        <CopyButton value={text} label={title} />
      </div>
      <pre className="max-h-96 overflow-auto rounded-md border border-border bg-muted/40 p-3 font-mono text-xs leading-5">
        {text}
      </pre>
    </div>
  );
}

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

/* Per-tool one-liner (Task 6 brief): a short, honest summary of the
   answer's most load-bearing field for that tool family. Tool names are
   matched by substring because the recorded field carries the MCP tool
   name verbatim (for example classify_ai_system, get_applicable_requirements,
   evaluate_project_evidence), never a shortened or invented label. Any tool
   outside the three named families falls back to listing the answer's own
   top-level keys, exactly as the brief specifies, rather than guessing at
   a summary. */
function toolOneLiner(tool: string, envelope: SessionEnvelope): string {
  const answer = asRecord(envelope.answer);
  if (tool.includes("classify")) {
    const risk = typeof answer.risk_category === "string" ? answer.risk_category : "not recorded";
    const fria = asRecord(answer.fria);
    const applicability =
      typeof fria.applicability === "string" ? fria.applicability : "not recorded";
    return `risk_category: ${risk}; FRIA applicability: ${applicability}`;
  }
  if (tool.includes("requirement")) {
    const byArticle = answer.requirements_by_article;
    const groups =
      byArticle !== null && typeof byArticle === "object" ? Object.keys(byArticle).length : 0;
    return `${groups} article group${groups === 1 ? "" : "s"} of requirements returned`;
  }
  if (tool.includes("evidence")) {
    const status = typeof envelope.status === "string" ? envelope.status : "not recorded";
    return `calibrated status: ${status}`;
  }
  const keys = Object.keys(answer);
  return keys.length > 0 ? `answer keys: ${keys.join(", ")}` : "answer has no top-level keys";
}

function ExchangeView({
  lines,
  index,
  onIndexChange,
}: {
  lines: SessionLine[];
  index: number;
  onIndexChange: (next: number) => void;
}) {
  const current = lines[index];
  const envelope = current.envelope ?? {};
  const missingFacts = Array.isArray(envelope.missing_facts) ? envelope.missing_facts : [];
  const status = typeof envelope.status === "string" ? envelope.status : null;
  const confidence = typeof envelope.confidence === "number" ? envelope.confidence : null;
  const judgeVerdict =
    typeof envelope.judge_verdict === "string" ? envelope.judge_verdict : "not recorded";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border bg-muted/30 px-3 py-2">
        <div className="flex items-center gap-2">
          <button
            type="button"
            className={ICON_BUTTON_SM}
            onClick={() => onIndexChange(Math.max(0, index - 1))}
            disabled={index === 0}
            aria-label="Previous exchange"
          >
            <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
          <span className="text-xs font-medium" aria-live="polite">
            Exchange {index + 1} of {lines.length}
          </span>
          <button
            type="button"
            className={ICON_BUTTON_SM}
            onClick={() => onIndexChange(Math.min(lines.length - 1, index + 1))}
            disabled={index === lines.length - 1}
            aria-label="Next exchange"
          >
            <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
          <span>seq {current.seq}</span>
          <span className="font-mono">{current.ts}</span>
          {current.repo_ref != null && (
            <span className="font-mono">repo_ref {JSON.stringify(current.repo_ref)}</span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="space-y-4 rounded-lg border border-border bg-card p-4">
          <p className="text-xs font-semibold text-muted-foreground">
            Raw, exactly as recorded
          </p>
          <JsonPane title="Request" value={current.request} />
          <JsonPane title="Envelope" value={current.envelope} />
        </div>

        <div className="space-y-3 rounded-lg border border-border bg-card p-4">
          <p className="text-xs font-semibold text-muted-foreground">Rendered meaning</p>
          <div className="flex flex-wrap items-center gap-2">
            <code className="rounded-md bg-muted px-2 py-1 font-mono text-xs font-semibold">
              {current.tool}
            </code>
            {status !== null ? (
              <StatusBadge status={status} />
            ) : (
              <span className="text-xs text-muted-foreground">status not recorded</span>
            )}
            <span className="text-xs text-muted-foreground">
              confidence {confidence !== null ? confidence : "not recorded"}
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            Judge verdict: <code className="font-mono">{judgeVerdict}</code>
          </p>
          <p className="text-sm">{toolOneLiner(current.tool, envelope)}</p>
          <div>
            <p className="text-xs font-semibold">Missing facts</p>
            {missingFacts.length === 0 ? (
              <p className="text-xs text-muted-foreground">none recorded</p>
            ) : (
              <ul className="list-disc pl-5 space-y-1 text-xs text-muted-foreground">
                {missingFacts.map((fact, i) => (
                  <li key={i}>{String(fact)}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function AgentPage() {
  const [listState, setListState] = useState<ListState>({ kind: "loading" });
  const [selected, setSelected] = useState<string | null>(null);
  const [sessionState, setSessionState] = useState<SessionState>({ kind: "idle" });
  const [index, setIndex] = useState(0);

  useEffect(() => {
    let cancelled = false;
    fetch(`${FACADE_URL}/api/demo/sessions`)
      .then(async (res) => {
        if (res.status === 404) {
          const data = await res.json().catch(() => null);
          if (!cancelled) {
            setListState({
              kind: "disabled",
              message:
                data && typeof data.error === "string" ? data.error : "demo sessions not enabled",
            });
          }
          return;
        }
        if (!res.ok) throw new Error(`facade error ${res.status}`);
        const data = await res.json();
        if (!cancelled) {
          setListState({
            kind: "ready",
            sessions: Array.isArray(data.sessions) ? data.sessions : [],
          });
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setListState({
            kind: "error",
            message: err instanceof Error ? err.message : String(err),
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function selectSession(name: string) {
    setSelected(name);
    setIndex(0);
    setSessionState({ kind: "loading" });
    fetch(`${FACADE_URL}/api/demo/sessions/${encodeURIComponent(name)}`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`facade error ${res.status}`);
        const text = await res.text();
        /* Parsed per raw file line (1-indexed on the split of the whole
           file, blank lines counted), never per non-blank line, so the
           reported number is the one a human opening the file in an
           editor would see. A malformed line fails the whole session
           visibly, naming the offending line, rather than a generic
           SyntaxError whose position refers to the inside of that one
           line's string. */
        const rawLines = text.split("\n");
        const lines: SessionLine[] = [];
        for (let i = 0; i < rawLines.length; i++) {
          const trimmed = rawLines[i].trim();
          if (trimmed.length === 0) continue;
          try {
            lines.push(JSON.parse(trimmed) as SessionLine);
          } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            throw new Error(`Line ${i + 1} of the session file is not valid JSON: ${message}`);
          }
        }
        setSessionState({ kind: "ready", lines });
      })
      .catch((err) => {
        setSessionState({
          kind: "error",
          message: err instanceof Error ? err.message : String(err),
        });
      });
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mx-auto max-w-4xl space-y-8">
        <div className="space-y-2">
          <h1 className="text-3xl font-bold tracking-tight">Agent</h1>
          <p className="text-sm text-muted-foreground">
            Step through recorded MCP exchanges from real example development. Each step
            shows the raw request and envelope exactly as recorded on the left, and a
            rendered summary on the right. Served read-only from the local facade at{" "}
            <code className="font-mono">{FACADE_URL}</code>.
          </p>
        </div>

        {listState.kind === "loading" && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            Loading recorded sessions...
          </div>
        )}

        {listState.kind === "error" && (
          <div className="space-y-2 rounded-lg border border-border bg-card p-6">
            <div className="flex items-center gap-2 text-sm font-medium text-destructive">
              <AlertCircle className="h-4 w-4" aria-hidden="true" />
              Could not reach the facade
            </div>
            <p className="text-sm text-muted-foreground">{listState.message}</p>
          </div>
        )}

        {listState.kind === "disabled" && (
          <div className="space-y-3 rounded-lg border border-dashed border-border bg-muted/30 p-6">
            <div className="flex items-center gap-2 text-sm font-medium">
              <AlertCircle className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
              Session replay is not enabled on this facade
            </div>
            <p className="text-sm text-muted-foreground">
              Set <code className="font-mono">{SESSIONS_ENV_VAR}</code> to a folder of
              recorded session files (for example{" "}
              <code className="font-mono">{EXAMPLE_SESSIONS_DIR}</code>), then restart the
              facade.
            </p>
            <p className="text-xs text-muted-foreground">{listState.message}</p>
          </div>
        )}

        {listState.kind === "ready" && (
          <div className="space-y-4">
            {listState.sessions.length === 0 ? (
              <div className="space-y-2 rounded-lg border border-dashed border-border bg-muted/30 p-6">
                <p className="text-sm font-medium">No recorded sessions yet</p>
                <p className="text-sm text-muted-foreground">
                  <code className="font-mono">{SESSIONS_ENV_VAR}</code> is set but the
                  directory has no <code className="font-mono">.jsonl</code> files. Example
                  consumer scripts append to{" "}
                  <code className="font-mono">{EXAMPLE_SESSIONS_DIR}</code> as they run.
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                <p className="text-sm font-medium leading-none">Recorded sessions</p>
                <div className="flex flex-wrap gap-2">
                  {listState.sessions.map((name) => (
                    <button
                      key={name}
                      type="button"
                      onClick={() => selectSession(name)}
                      aria-pressed={selected === name}
                      className={
                        "rounded-md border px-3 py-1.5 font-mono text-xs transition-colors " +
                        (selected === name
                          ? "border-primary/40 bg-accent text-accent-foreground"
                          : "border-input text-muted-foreground hover:bg-accent hover:text-accent-foreground")
                      }
                    >
                      {name}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {sessionState.kind === "loading" && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                Loading session...
              </div>
            )}
            {sessionState.kind === "error" && (
              <p className="text-sm text-destructive">{sessionState.message}</p>
            )}
            {sessionState.kind === "ready" && sessionState.lines.length === 0 && (
              <p className="text-sm text-muted-foreground">
                This session file has no recorded exchanges.
              </p>
            )}
            {sessionState.kind === "ready" && sessionState.lines.length > 0 && (
              <ExchangeView
                lines={sessionState.lines}
                index={Math.min(index, sessionState.lines.length - 1)}
                onIndexChange={setIndex}
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
}
