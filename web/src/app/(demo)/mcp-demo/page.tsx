import Link from "next/link";
import { loadDemoIndex, type DemoSystem } from "./data";

/* MCP demo index (docs/architecture.md Sections 8 and 9). Five sessions were
   recorded against the TERE4AI MCP server over stdio, the same transport a
   coding agent uses, one per EU AI Act risk tier plus one abstention case.
   This page lists them; each card opens the recorded report. Nothing here is
   live: the answers were recorded once and are shown exactly as returned. */

export const metadata = {
  title: "MCP demo",
};

function SetupNotice() {
  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-4xl mx-auto space-y-4">
        <h1 className="text-3xl font-semibold tracking-tight">
          Recorded sessions not generated yet
        </h1>
        <p className="text-sm text-muted-foreground max-w-[70ch]">
          public/mcp-demo/index.json is missing or unreadable, so there are no
          recorded answers to show. Nothing has been generated, and this page
          never shows a zero as if it were a recorded count.
        </p>
        <div className="rounded-lg border border-border bg-card p-5 space-y-2">
          <p className="text-xs font-medium tracking-wide text-muted-foreground">
            generate it
          </p>
          <pre className="overflow-x-auto rounded-md bg-muted p-3 font-mono text-xs">
            {`python scripts/record_mcp_demo.py
python scripts/build_mcp_demo_index.py
for k in minimalrisk limitedrisk highrisk unacceptablerisk abstention; do
  python -m tere4ai.report demo/mcp_demo/sessions/$k.jsonl \\
    -o web/public/mcp-demo/$k.html
done`}
          </pre>
        </div>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string | null }) {
  if (!status) return null;
  const cls =
    status === "requires_human_review"
      ? "text-foreground border-border border-dashed"
      : "text-foreground border-border";
  return (
    <span className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${cls}`}>
      {status}
    </span>
  );
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <code className="rounded-md bg-muted px-1.5 py-0.5 font-mono text-xs break-all">
      {children}
    </code>
  );
}

function Figure({
  label,
  value,
  qualifier,
}: {
  label: string;
  value: string;
  qualifier?: string;
}) {
  return (
    <div className="space-y-0.5">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className="text-base font-semibold tabular-nums break-words sm:text-2xl">
        {value}
      </p>
      {qualifier ? (
        <p className="text-xs text-muted-foreground">{qualifier}</p>
      ) : null}
    </div>
  );
}

function SystemCard({ system }: { system: DemoSystem }) {
  const req = system.requirements;
  const trace = system.trace;
  /* A classification the server left for human review does not settle the
     tier, so the requirement count beside it is provisional. Say so rather
     than letting the number read as final. */
  const provisional =
    system.classification.status === "requires_human_review";
  const reqQualifier = req.articles
    ? `across ${req.articles} articles${provisional ? ", tier not settled" : ""}`
    : "none returned";
  return (
    <Link
      href={`/mcp-demo/${system.key}`}
      className="block rounded-lg border border-border bg-card p-5 shadow-sm transition-colors hover:bg-muted/40"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <p className="text-xs font-medium tracking-wide text-muted-foreground">
            {system.label}
          </p>
          <h2 className="text-xl font-semibold">{system.product}</h2>
        </div>
        <StatusBadge status={system.classification.status} />
      </div>

      <p className="mt-3 max-w-[70ch] text-sm text-muted-foreground">
        {system.blurb}
      </p>

      <div className="mt-5 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Figure
          label="risk_category"
          value={system.classification.risk_category ?? "not recorded"}
          qualifier={
            system.classification.confidence !== null
              ? `confidence ${system.classification.confidence}`
              : undefined
          }
        />
        <Figure
          label="requirements"
          value={req.returned === null ? "not recorded" : String(req.returned)}
          qualifier={reqQualifier}
        />
        <Figure
          label="traced to code"
          value={
            trace && trace.traced !== null
              ? `${trace.traced} of ${trace.applicable_norms}`
              : "not recorded"
          }
          qualifier={
            trace && trace.invalid_tags
              ? `${trace.invalid_tags} tag refused`
              : trace
                ? "no tag refused"
                : "no trace call in this session"
          }
        />
        <Figure
          label="MCP calls"
          value={String(system.exchanges.length)}
          qualifier="recorded over stdio"
        />
      </div>

      <p className="mt-4 flex flex-wrap gap-1.5">
        {system.classification.source_nodes.slice(0, 3).map((node) => (
          <Chip key={node}>{node}</Chip>
        ))}
      </p>
    </Link>
  );
}

export default function McpDemoPage() {
  const index = loadDemoIndex();
  if (!index) return <SetupNotice />;

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mx-auto max-w-5xl space-y-8">
        <header className="space-y-3">
          <p className="text-xs font-medium tracking-wide text-muted-foreground">
            recorded MCP sessions
          </p>
          <h1 className="text-3xl font-semibold tracking-tight">MCP demo</h1>
          <p className="max-w-[70ch] text-sm text-muted-foreground">
            Five AI systems were put to the TERE4AI MCP server over stdio, the
            same transport a coding agent uses, one per EU AI Act risk tier plus
            one case where the facts do not settle the tier. Only free
            deterministic tools were called: no model decided any answer, and no
            paid call was made. Each report below is the recorded session
            rendered as one self-contained document, answers exactly as the
            server returned them.
          </p>
          <p className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span>graph</span>
            {index.graph_versions.map((v) => (
              <Chip key={v}>{v}</Chip>
            ))}
          </p>
        </header>

        <div className="space-y-4">
          {index.systems.map((system) => (
            <SystemCard key={system.key} system={system} />
          ))}
        </div>

        <section className="rounded-lg border border-border bg-card p-5 space-y-3">
          <h2 className="text-xl font-semibold">How to read these</h2>
          <ul className="max-w-[70ch] list-disc space-y-2 pl-5 text-sm text-muted-foreground">
            <li>
              The risk tier is decided by a fixed rule ladder, never by a model.
              A fact the ladder needs and does not have is reported in
              missing_facts rather than assumed.
            </li>
            <li>
              A prohibited system receives zero engineering requirements. No
              backlog can make a banned practice permissible, so the answer
              carries the prohibition citation and nothing else.
            </li>
            <li>
              Every citation resolves to a byte range in a checksummed snapshot
              of the Official Journal text. The reports carry the span id, the
              snapshot file, and the offsets.
            </li>
            <li>
              A trace between a requirement and a line of code is a developer
              claim, not evidence. It never raises an evidence status.
            </li>
          </ul>
        </section>
      </div>
    </div>
  );
}
