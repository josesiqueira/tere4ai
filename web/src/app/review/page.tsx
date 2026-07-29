import fs from "node:fs";
import path from "node:path";

/* Read-only review-queue page (docs/architecture.md Sections 9 and 13).
   Renders the human-review backlog from public/ui_data.json: norms whose
   extraction judge said needs_human_review, plus pending cross-reference and
   alignment counts. Items shown here carry status requires_human_review and
   are never served as requirements; this page only makes the queue visible,
   adjudication happens through scripts/review_queue.py. */

type ReviewNorm = {
  norm_id: string;
  source_node_id: string;
  source_span_id: string;
  deontic_type: string;
  modal: string;
  actor: string | null;
  actor_source: string;
  action: string;
  object: string;
  conditions: string[];
  confidence: number | null;
  judge_verdict: string;
  review_status: string;
};

type UiData = {
  coverage: { graph_version: string; generated_at: string };
  build: { build_id: string };
  review: {
    norms_needing_review: ReviewNorm[];
    crossref_pending_total: number;
    crossref_pending_by_kind: Record<string, number>;
    alignment_pending_total: number;
  };
};

/* Guarded read: public/ui_data.json is generated (gitignored, not committed),
   so a fresh clone or a dev server started before the export script has run
   must not 500. Catch the read or parse failure and let ReviewPage() render
   an honest setup notice instead of fabricating a queue. */
function loadData(): UiData | null {
  const p = path.join(process.cwd(), "public", "ui_data.json");
  try {
    return JSON.parse(fs.readFileSync(p, "utf-8"));
  } catch {
    return null;
  }
}

function SetupNotice() {
  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-4xl mx-auto space-y-8">
        <div className="space-y-2">
          <h1 className="text-3xl font-bold tracking-tight">
            Demo data not generated yet
          </h1>
          <p className="text-sm text-muted-foreground">
            public/ui_data.json is missing or unreadable, so there is no
            review queue to show. This is not an error state with a hidden
            queue behind it: nothing has been generated, and this page never
            shows a zero as if it were a real count.
          </p>
        </div>
        <section className="rounded-lg border border-border bg-card text-card-foreground shadow-sm p-6 space-y-4">
          <h2 className="text-2xl font-semibold leading-none">Generate it</h2>
          <p className="text-sm text-muted-foreground">
            From the repo root, run:
          </p>
          <pre className="rounded-md bg-muted p-2 text-sm font-mono overflow-x-auto">
            .venv/bin/python scripts/export_ui_data.py
          </pre>
          <p className="text-sm text-muted-foreground">
            Then reload this page. `npm run dev` (invoked from web/) runs
            this command automatically before the server starts, so this
            notice should only appear if the export itself failed or the
            file was deleted after the server started.
          </p>
        </section>
      </div>
    </div>
  );
}

function CountTile({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-border bg-card text-card-foreground shadow-sm p-4">
      <p className="text-2xl font-semibold leading-none">{value}</p>
      <p className="mt-1.5 text-xs text-muted-foreground">{label}</p>
    </div>
  );
}

export default function ReviewPage() {
  const data = loadData();
  if (!data) {
    return <SetupNotice />;
  }
  const r = data.review;
  const kinds = Object.entries(r.crossref_pending_by_kind).sort();

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-4xl mx-auto space-y-8">
        <div className="space-y-2">
          <h1 className="text-3xl font-bold tracking-tight">Human review queue</h1>
          <p className="text-sm text-muted-foreground">
            Graph version <code className="font-mono">{data.coverage.graph_version}</code>,
            build <code className="font-mono">{data.build.build_id}</code>. Every item
            below has status{" "}
            <span className="rounded-full border border-border px-2.5 py-0.5 text-xs font-semibold">
              requires_human_review
            </span>{" "}
            and is excluded from runtime answers until a human adjudicates it.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <CountTile label="norms needing review" value={r.norms_needing_review.length} />
          <CountTile label="alignments pending" value={r.alignment_pending_total} />
          <CountTile label="cross-reference items" value={r.crossref_pending_total} />
        </div>
        <p className="text-xs text-muted-foreground">
          Cross-reference items by kind:{" "}
          {kinds.map(([k, v]) => `${k} ${v}`).join(", ")}. Alignments pending are
          judge-rejected assertions held for human confirmation, never served as
          accepted mappings.
        </p>

        <section className="rounded-lg border border-border bg-card text-card-foreground shadow-sm p-6 space-y-4">
          <h2 className="text-2xl font-semibold leading-none">
            Norms flagged by the extraction judge
          </h2>
          <p className="text-sm text-muted-foreground">
            Each norm cites its exact source span; the judge verdict{" "}
            <code className="font-mono">needs_human_review</code> means the deontic
            reading was not fully supported by the text and a human must accept or
            reject it.
          </p>
          <div className="space-y-2">
            {r.norms_needing_review.map((n) => (
              <details key={n.norm_id} className="rounded-md border border-border">
                <summary className="cursor-pointer p-3 text-sm hover:bg-accent flex flex-wrap items-center gap-2">
                  <code className="font-mono text-xs text-muted-foreground break-all">
                    {n.norm_id}
                  </code>
                  <span className="rounded-full border border-border px-2.5 py-0.5 text-xs font-semibold">
                    {n.deontic_type}
                  </span>
                  <span className="rounded-full border border-border px-2.5 py-0.5 text-xs font-semibold text-muted-foreground">
                    {n.actor ?? "actor unknown"} ({n.actor_source})
                  </span>
                </summary>
                <div className="p-3 pt-0 space-y-2 text-sm">
                  <p>
                    <span className="font-semibold">{n.action}</span> {n.object}
                  </p>
                  {n.conditions.length > 0 && (
                    <p className="text-muted-foreground">
                      Conditions: {n.conditions.join("; ")}
                    </p>
                  )}
                  <dl className="grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-1 text-xs">
                    <div>
                      <dt className="text-muted-foreground inline">Source span: </dt>
                      <dd className="font-mono inline break-all">{n.source_span_id}</dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground inline">Source node: </dt>
                      <dd className="font-mono inline break-all">{n.source_node_id}</dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground inline">Modal: </dt>
                      <dd className="font-mono inline">{n.modal}</dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground inline">Judge verdict: </dt>
                      <dd className="font-mono inline">{n.judge_verdict}</dd>
                    </div>
                    {n.confidence != null && (
                      <div>
                        <dt className="text-muted-foreground inline">
                          Extractor confidence:{" "}
                        </dt>
                        <dd className="font-mono inline">{n.confidence}</dd>
                      </div>
                    )}
                  </dl>
                </div>
              </details>
            ))}
          </div>
        </section>

        <p className="text-xs text-muted-foreground">
          Adjudication is done offline with scripts/review_queue.py; decisions are
          written back with HUMAN_REVIEWED provenance and republished in the next
          versioned build. This page never writes to the graph.
        </p>
      </div>
    </div>
  );
}
