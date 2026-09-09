import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { loadDemoIndex, findSystem, type Claim, type DemoSystem } from "../data";

/* One recorded MCP session (docs/architecture.md Sections 8 and 9): the header
   figures, the two directions of the DEC-15 traceability record, and the full
   rendered report embedded from public/mcp-demo/<key>.html. Every value comes
   from public/mcp-demo/index.json, which is derived from the recorded
   envelopes, so this page cannot state a figure the server did not answer. */

export function generateStaticParams() {
  const index = loadDemoIndex();
  return (index?.systems ?? []).map((s) => ({ tier: s.key }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ tier: string }>;
}) {
  const { tier } = await params;
  const index = loadDemoIndex();
  const system = index ? findSystem(index, tier) : undefined;
  return { title: system ? `${system.product} MCP session` : "MCP demo" };
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
      {qualifier ? <p className="text-xs text-muted-foreground">{qualifier}</p> : null}
    </div>
  );
}

function ClaimRow({ claim }: { claim: Claim }) {
  if (!claim.accepted) {
    return (
      <li className="rounded-md border border-dashed border-border p-3 space-y-1.5">
        <p className="flex flex-wrap items-center gap-2 text-xs">
          <span className="font-mono text-muted-foreground">line {claim.line}</span>
          <Chip>{claim.norm_id}</Chip>
          <span className="rounded-full border border-dashed border-border px-2.5 py-0.5 text-xs font-medium">
            tag refused
          </span>
        </p>
        <p className="max-w-[75ch] text-sm text-muted-foreground">
          {claim.refusal_reason}
        </p>
      </li>
    );
  }
  return (
    <li className="rounded-md border border-border p-3 space-y-1.5">
      <p className="flex flex-wrap items-center gap-2 text-xs">
        <span className="font-mono text-muted-foreground">line {claim.line}</span>
        <Chip>{claim.norm_id}</Chip>
        {claim.source_span_id ? <Chip>{claim.source_span_id}</Chip> : null}
      </p>
      <p className="max-w-[75ch] text-sm">
        <span className="text-muted-foreground">{claim.modal} </span>
        {claim.action} {claim.object}
      </p>
    </li>
  );
}

function CodeToRequirements({ system }: { system: DemoSystem }) {
  const trace = system.trace;
  if (!trace) return null;
  return (
    <section className="rounded-lg border border-border bg-card p-5 space-y-4">
      <div className="space-y-1">
        <p className="text-xs font-medium tracking-wide text-muted-foreground">
          code to requirements
        </p>
        <h2 className="text-xl font-semibold">What each file claims</h2>
        <p className="max-w-[70ch] text-sm text-muted-foreground">
          The same recorded matrix read from the code side: for every file
          carrying a tag, which norms it claims and at which line. The tag
          convention is <Chip>{trace.tag_convention}</Chip>, scanned in the
          project checkout, because the server never reads a consumer file
          system. A tag citing a norm that is not judge-accepted is reported
          with the server's own reason and never joined.
        </p>
      </div>

      <div className="space-y-4">
        {trace.code_index.map((file) => (
          <div key={file.path} className="space-y-2">
            <p className="font-mono text-sm break-all">
              {system.repo_ref ? `${system.repo_ref}/` : ""}
              {file.path}
            </p>
            <ul className="space-y-2">
              {file.claims.map((claim, i) => (
                <ClaimRow key={`${claim.norm_id}-${claim.line}-${i}`} claim={claim} />
              ))}
            </ul>
          </div>
        ))}
      </div>

      {trace.trace_note ? (
        <p className="max-w-[70ch] rounded-lg border border-border bg-muted/50 p-3 text-xs text-muted-foreground">
          {trace.trace_note}
        </p>
      ) : null}
    </section>
  );
}

export default async function TierPage({
  params,
}: {
  params: Promise<{ tier: string }>;
}) {
  const { tier } = await params;
  const index = loadDemoIndex();
  if (!index) notFound();
  const system = findSystem(index, tier);
  if (!system) notFound();

  const req = system.requirements;
  const trace = system.trace;
  /* A classification the server left for human review does not settle the
     tier, so the requirement count beside it is provisional. */
  const provisional =
    system.classification.status === "requires_human_review";
  const reqQualifier = req.articles
    ? `across ${req.articles} articles${provisional ? ", tier not settled" : ""}`
    : "none returned";

  /* The recorded per_article map is serialized with sorted keys, so
     "article-10" precedes "article-8" as a string. Order the table by the
     article's number instead, which is the order a reader expects. */
  /* The recorded missing_facts list mixes Article 5 prohibition-relevant
     unknowns with Annex III high-risk ones. The status line above says the
     Article 5 unknowns are the ones that could change the outcome to
     prohibited, so show those first. Order only: no text is altered and
     nothing is dropped. */
  const missingFacts = [...system.classification.missing_facts].sort(
    (a, b) =>
      Number(b.includes("Article 5")) - Number(a.includes("Article 5")),
  );
  const articles = Object.entries(req.per_article).sort(
    (a, b) => Number(a[0].replace(/\D/g, "")) - Number(b[0].replace(/\D/g, "")),
  );

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mx-auto max-w-5xl space-y-8">
        <Link
          href="/mcp-demo"
          className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          All recorded sessions
        </Link>

        <header className="space-y-3">
          <p className="text-xs font-medium tracking-wide text-muted-foreground">
            {system.label}
          </p>
          <h1 className="text-3xl font-semibold tracking-tight">{system.product}</h1>
          <p className="max-w-[70ch] text-sm text-muted-foreground">{system.blurb}</p>
        </header>

        <section className="grid grid-cols-2 gap-6 sm:grid-cols-4">
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
            label="requirements returned"
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
              trace
                ? `${trace.untraced} untraced, ${trace.invalid_tags} refused`
                : "no trace call in this session"
            }
          />
          <Figure
            label="Article 27 assessment"
            value={system.classification.fria ?? "not recorded"}
            qualifier="deployer duty"
          />
        </section>

        <section className="rounded-lg border border-border bg-card p-5 space-y-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-xl font-semibold">What the ladder decided</h2>
            <StatusBadge status={system.classification.status} />
          </div>
          <ul className="max-w-[75ch] space-y-2 text-sm">
            {system.classification.rationale.map((line) => (
              <li key={line} className="rounded-md border border-border p-3">
                {line}
              </li>
            ))}
          </ul>
          {missingFacts.length > 0 ? (
            <div className="space-y-2">
              <p className="text-xs font-medium tracking-wide text-muted-foreground">
                facts the ladder asked for and did not have
              </p>
              <ul className="max-w-[75ch] space-y-1.5 text-sm text-muted-foreground">
                {missingFacts.map((fact) => (
                  <li
                    key={fact}
                    className="rounded-md border border-dashed border-border px-3 py-2"
                  >
                    {fact}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {req.message ? (
            <div className="space-y-1.5">
              <p className="text-xs font-medium tracking-wide text-muted-foreground">
                recorded message from get_applicable_requirements
              </p>
              <p className="max-w-[75ch] rounded-lg border border-border bg-muted/50 p-3 text-sm">
                {req.message}
              </p>
            </div>
          ) : null}
        </section>

        <section className="rounded-lg border border-border bg-card p-5 space-y-3">
          <h2 className="text-xl font-semibold">The calls that were made</h2>
          <p className="max-w-[70ch] text-sm text-muted-foreground">
            Recorded in order against the running server. The full request and
            envelope of each one is in the report below.
          </p>
          <ol className="space-y-1.5">
            {system.exchanges.map((ex) => (
              <li
                key={ex.seq}
                className="flex flex-wrap items-center gap-2 rounded-md border border-border px-3 py-2 text-sm"
              >
                <span className="font-mono text-xs text-muted-foreground">
                  {ex.seq}
                </span>
                <span className="font-mono">{ex.tool}</span>
                <StatusBadge status={ex.status} />
              </li>
            ))}
          </ol>
        </section>

        {articles.length > 0 ? (
          <section className="rounded-lg border border-border bg-card p-5 space-y-3">
            <div className="space-y-1">
              <p className="text-xs font-medium tracking-wide text-muted-foreground">
                requirements to code
              </p>
              <h2 className="text-xl font-semibold">Every article in scope</h2>
              <p className="max-w-[70ch] text-sm text-muted-foreground">
                Judge-accepted norms per article, as returned. Norms still in
                human review are counted beside them and are never served as
                requirements. The full text of each norm, its source span, and
                the row saying whether code claims it are in the report below.
              </p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[26rem] text-sm">
                <thead>
                  <tr className="border-b border-border text-left">
                    <th className="py-2 pr-4 font-medium">Article</th>
                    <th className="py-2 pr-4 font-medium tabular-nums">Accepted</th>
                    <th className="py-2 font-medium tabular-nums">In human review</th>
                  </tr>
                </thead>
                <tbody>
                  {articles.map(([article, counts]) => (
                    <tr key={article} className="border-b border-border last:border-0">
                      <td className="py-2 pr-4 font-mono text-xs">{article}</td>
                      <td className="py-2 pr-4 tabular-nums">{counts.accepted}</td>
                      <td className="py-2 tabular-nums">{counts.needs_human_review}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ) : null}

        <CodeToRequirements system={system} />

        <section className="space-y-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <div className="space-y-1">
              <p className="text-xs font-medium tracking-wide text-muted-foreground">
                recorded session
              </p>
              <h2 className="text-xl font-semibold">The full report</h2>
            </div>
            <a
              href={system.report}
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-9 items-center gap-2 rounded-md border border-border px-4 text-sm font-medium hover:bg-muted"
            >
              Open on its own
              <ExternalLink className="h-4 w-4" aria-hidden="true" />
            </a>
          </div>
          <p className="max-w-[70ch] text-sm text-muted-foreground">
            One self-contained document rendered from{" "}
            <Chip>{system.session_file}</Chip>. It carries every request, every
            envelope, the byte-exact source quotes with their checksums, and the
            full traceability matrix.
          </p>
          <iframe
            src={system.report}
            title={`${system.product} recorded MCP session report`}
            className="h-[80vh] w-full rounded-lg border border-border bg-background"
          />
        </section>
      </div>
    </div>
  );
}
