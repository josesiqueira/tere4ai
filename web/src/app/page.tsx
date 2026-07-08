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
      layer2_nodes: { count: number; status: string };
      layer3_nodes: { count: number; status: string };
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
  build: { build_id: string; built_at: string; snapshots: { file: string; sha256: string }[] };
  review_queue_count: number;
  sources: { id: string; title: string; legal_status: string }[];
};

function loadData(): UiData {
  const p = path.join(process.cwd(), "public", "ui_data.json");
  return JSON.parse(fs.readFileSync(p, "utf-8"));
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

export default function Page() {
  const data = loadData();
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

        <Card title="Coverage matrix">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-muted-foreground">
                <th className="py-1 font-medium">Element</th>
                <th className="py-1 font-medium">Expected</th>
                <th className="py-1 font-medium">In graph</th>
                <th className="py-1 font-medium">Check</th>
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
                <td className="py-1.5">Layer 2 normative nodes</td>
                <td className="py-1.5 font-mono">0 (M1)</td>
                <td className="py-1.5 font-mono">{a.layer2_nodes.count}</td>
                <td className="py-1.5 text-muted-foreground">
                  {a.layer2_nodes.status} (M2)
                </td>
              </tr>
              <tr className="border-t border-border">
                <td className="py-1.5">Layer 3 ethics nodes</td>
                <td className="py-1.5 font-mono">0 (M1)</td>
                <td className="py-1.5 font-mono">{a.layer3_nodes.count}</td>
                <td className="py-1.5 text-muted-foreground">
                  {a.layer3_nodes.status} (M2)
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
