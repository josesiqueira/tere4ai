import fs from "node:fs";
import path from "node:path";

/* Thin, read-only demo page (docs/architecture.md Sections 9 and 14, M1).
   Renders the coverage matrix and the browsable Act structure from
   public/ui_data.json, which scripts/export_ui_data.py produces by calling
   the same coverage_report used by the MCP tool. Every screen shows the
   status vocabulary, judge verdict, graph version, and the legal notice. */

type Article = { id: string; number: number; title: string; anchor: string };
type Section = { id: string; number: number; title: string; articles: Article[] };
type Chapter = {
  id: string;
  number: string;
  title: string;
  sections: Section[];
  articles: Article[];
};

type UiData = {
  coverage: {
    answer: {
      expected: Record<string, number | string[]>;
      actual: Record<string, number | string[]>;
      high_risk_core: { expected_articles: number[]; present: number[]; missing: number[] };
      layer2_nodes: { count: number; status: string; verdicts?: Record<string, number> };
      layer3_nodes: { count: number; status: string; verdicts?: Record<string, number> };
      checks: Record<string, boolean>;
    };
    status: string;
    confidence: number;
    judge_verdict: string;
    generated_at: string;
    graph_version: string;
    legal_status_notes: string[];
    non_legal_advice_notice: string;
  };
  structure: {
    chapters: Chapter[];
    annexes: { id: string; number: string; title: string; anchor: string }[];
    recital_count: number;
  };
  build: {
    build_id: string;
    built_at: string;
    chain_id: string;
    snapshots: { file: string; sha256: string }[];
  };
  review_queue_count: number;
  sources: { id: string; title: string; legal_status: string }[];
};

/* Guarded read: public/ui_data.json is generated (gitignored, not committed),
   so a fresh clone or a dev server started before the export script has run
   must not 500. Catch the read or parse failure and let Page() render an
   honest setup notice instead of fabricating data. */
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
            coverage data to show. This is not an error state with hidden
            numbers behind it: nothing has been generated, and this page
            never shows a zero as if it were a real count.
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

function StatusBadge({ status }: { status: string }) {
  const ok = status === "satisfied_with_evidence";
  return (
    <span
      className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${
        ok
          ? "text-green-600 dark:text-green-400 border-green-600/40"
          : "text-destructive border-destructive/40"
      }`}
    >
      {status}
    </span>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-border bg-card text-card-foreground shadow-sm p-6 space-y-4">
      <h2 className="text-2xl font-semibold leading-none">{title}</h2>
      {children}
    </section>
  );
}

/* Numeric fields inside coverage.answer.actual are typed number | string[]
   (some, like "chapters", are arrays). Only surface fields that are actually
   numbers; never coerce or invent a count. */
function asNumber(v: number | string[] | undefined): number | undefined {
  return typeof v === "number" ? v : undefined;
}

function StatTiles({
  actual,
  layer2AcceptedCount,
  layer3AcceptedCount,
  reviewCount,
  buildId,
  builtAt,
  snapshotCount,
  chainId,
}: {
  actual: UiData["coverage"]["answer"]["actual"];
  layer2AcceptedCount: number | undefined;
  layer3AcceptedCount: number | undefined;
  reviewCount: number;
  buildId: string;
  builtAt: string;
  snapshotCount: number;
  chainId: string;
}) {
  const tiles: { label: string; value: number | undefined }[] = [
    { label: "Articles", value: asNumber(actual.articles) },
    { label: "Recitals", value: asNumber(actual.recitals) },
    { label: "Annexes", value: asNumber(actual.annexes) },
    { label: "Judge-accepted norms", value: layer2AcceptedCount },
    { label: "Accepted HLEG alignments", value: layer3AcceptedCount },
    { label: "Pending human review", value: reviewCount },
  ].filter((t) => t.value !== undefined);

  return (
    <section aria-label="Graph inventory" className="space-y-2">
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        {tiles.map((t) => (
          <div
            key={t.label}
            className="rounded-lg border border-border bg-card text-card-foreground shadow-sm p-4"
          >
            <div className="text-2xl font-semibold leading-none">{t.value}</div>
            <div className="mt-1.5 text-xs text-muted-foreground">{t.label}</div>
          </div>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">
        Build <code className="font-mono">{buildId}</code>, built{" "}
        {builtAt.slice(0, 19)}Z. {snapshotCount} frozen source files
        checksummed; publication chain{" "}
        <code className="font-mono">{chainId}</code>, recorded by the build
        and verified at server startup. Every count above is served from the
        published dump, not typed into this page. EU to HLEG mappings are
        LLM-generated and not expert-validated.
      </p>
    </section>
  );
}

export default function Page() {
  const data = loadData();
  if (!data) {
    return <SetupNotice />;
  }
  const { coverage, structure, build } = data;
  const a = coverage.answer;
  const rows: [string, number, number][] = Object.keys(a.expected)
    .map((k): [string, number, number] => {
      const exp = a.expected[k];
      const act = a.actual[k] ?? 0;
      const expN = Array.isArray(exp) ? exp.length : exp;
      const actN = Array.isArray(act) ? act.length : act;
      return [k, expN, actN];
    });

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-4xl mx-auto space-y-8">
        <div className="space-y-2">
          <h1 className="text-3xl font-bold tracking-tight">
            EU AI Act structural mirror
          </h1>
          <p className="text-sm text-muted-foreground">
            Graph version <code className="font-mono">{coverage.graph_version}</code>,
            generated {coverage.generated_at.slice(0, 19)}Z. Judge verdict:{" "}
            <code className="font-mono">{coverage.judge_verdict}</code> (structural
            answers are deterministic). <StatusBadge status={coverage.status} />
          </p>
        </div>

        <StatTiles
          actual={a.actual}
          layer2AcceptedCount={a.layer2_nodes.verdicts?.accepted}
          layer3AcceptedCount={a.layer3_nodes.verdicts?.accepted}
          reviewCount={data.review_queue_count}
          buildId={build.build_id}
          builtAt={build.built_at}
          snapshotCount={build.snapshots.length}
          chainId={build.chain_id}
        />

        <Card title="Coverage matrix">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-muted-foreground">
                <th scope="col" className="py-1 font-medium">Element</th>
                <th scope="col" className="py-1 font-medium">Expected</th>
                <th scope="col" className="py-1 font-medium">In graph</th>
                <th scope="col" className="py-1 font-medium">Check</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(([k, exp, act]) => (
                <tr key={k} className="border-t border-border">
                  <td className="py-1.5">{k}</td>
                  <td className="py-1.5 font-mono">{exp}</td>
                  <td className="py-1.5 font-mono">{act}</td>
                  <td className="py-1.5">
                    {act >= exp ? (
                      <span className="text-green-600 dark:text-green-400">pass</span>
                    ) : (
                      <span className="text-destructive">fail</span>
                    )}
                  </td>
                </tr>
              ))}
              <tr className="border-t border-border">
                <td className="py-1.5">Layer 2 judged norms (high-risk core)</td>
                <td className="py-1.5 font-mono">-</td>
                <td className="py-1.5 font-mono">{a.layer2_nodes.count}</td>
                <td className="py-1.5 text-muted-foreground">
                  {a.layer2_nodes.verdicts
                    ? `accepted ${a.layer2_nodes.verdicts.accepted ?? 0} / rejected ${a.layer2_nodes.verdicts.rejected ?? 0} / review ${a.layer2_nodes.verdicts.needs_human_review ?? 0}`
                    : a.layer2_nodes.status}
                </td>
              </tr>
              <tr className="border-t border-border">
                <td className="py-1.5">Layer 3 judged alignments (reified)</td>
                <td className="py-1.5 font-mono">-</td>
                <td className="py-1.5 font-mono">{a.layer3_nodes.count}</td>
                <td className="py-1.5 text-muted-foreground">
                  {a.layer3_nodes.verdicts
                    ? `accepted ${a.layer3_nodes.verdicts.accepted ?? 0} / rejected ${a.layer3_nodes.verdicts.rejected ?? 0}`
                    : a.layer3_nodes.status}
                </td>
              </tr>
            </tbody>
          </table>
          <p className="text-xs text-muted-foreground">
            High-risk core (Section 10 set): {a.high_risk_core.present.length} articles
            structurally present
            {a.high_risk_core.missing.length > 0
              ? `, missing: ${a.high_risk_core.missing.join(", ")}`
              : ", none missing"}
            . Cross-reference review queue: {data.review_queue_count} items awaiting
            judgement.
          </p>
        </Card>

        <Card title="Sources and versioning">
          <ul className="space-y-2 text-sm">
            {data.sources.map((s) => (
              <li key={s.id} className="flex items-start gap-2">
                <span
                  className={`mt-0.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${
                    s.legal_status === "in_force"
                      ? "text-green-600 dark:text-green-400 border-green-600/40"
                      : "text-muted-foreground border-border"
                  }`}
                >
                  {s.legal_status}
                </span>
                <span>{s.title}</span>
              </li>
            ))}
          </ul>
          <p className="text-xs text-muted-foreground font-mono break-all">
            snapshot {build.snapshots[0]?.file} sha256 {build.snapshots[0]?.sha256}
          </p>
        </Card>

        <Card title={`Act structure (${structure.recital_count} recitals precede)`}>
          <div className="space-y-1">
            {structure.chapters.map((c) => (
              <details key={c.id} className="rounded-md border border-border">
                <summary className="cursor-pointer p-3 text-sm font-medium hover:bg-accent">
                  Chapter {c.number}: {c.title || "(untitled)"}
                </summary>
                <div className="p-3 pt-0 space-y-2">
                  {c.sections.map((s) => (
                    <div key={s.id} className="space-y-1">
                      <p className="text-sm font-semibold">
                        Section {s.number}: {s.title || ""}
                      </p>
                      <ul className="pl-4 space-y-1">
                        {s.articles.map((art) => (
                          <li key={art.id} className="text-sm leading-6">
                            <span className="font-mono text-xs text-muted-foreground mr-2">
                              {art.id}
                            </span>
                            Article {art.number}: {art.title}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                  {c.articles.length > 0 && (
                    <ul className="space-y-1">
                      {c.articles.map((art) => (
                        <li key={art.id} className="text-sm leading-6">
                          <span className="font-mono text-xs text-muted-foreground mr-2">
                            {art.id}
                          </span>
                          Article {art.number}: {art.title}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </details>
            ))}
          </div>
          <div className="pt-2">
            <p className="text-sm font-semibold pb-1">Annexes</p>
            <ul className="grid grid-cols-1 md:grid-cols-2 gap-1">
              {structure.annexes.map((x) => (
                <li key={x.id} className="text-sm leading-6">
                  <span className="font-mono text-xs text-muted-foreground mr-2">
                    {x.id}
                  </span>
                  Annex {x.number}
                </li>
              ))}
            </ul>
          </div>
        </Card>

      </div>
    </div>
  );
}
