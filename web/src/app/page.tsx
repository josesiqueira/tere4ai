import Link from "next/link";
import Image from "next/image";

/* The landing page: the front door of the system. Full-bleed (outside the
   (demo) route group), clinical-blueprint system per docs/DESIGN.md. Every
   header item is a real destination into the demo, never a scroll anchor:
   the landing explains, the demo shows. */

const GITHUB = "https://github.com/josesiqueira/tere4ai";

const NOTICE =
  "TERE4AI provides engineering and documentation support. It does not " +
  "certify EU AI Act compliance and does not replace legal review, " +
  "conformity assessment, or competent-authority interpretation.";

function ChainLink({ level, value, meta }: { level: string; value: string; meta?: string }) {
  return (
    <div className="flex-1 min-w-[168px] rounded-sm border border-border bg-sidebar px-3.5 py-3">
      <div className="text-[10.5px] font-medium uppercase tracking-[0.05em] text-muted-foreground">
        {level}
      </div>
      <div className="mt-1.5 font-mono text-[12.5px] leading-relaxed break-words">
        {value}
        {meta ? <span className="text-muted-foreground"> {meta}</span> : null}
      </div>
    </div>
  );
}

function Arrow() {
  return (
    <div className="grid place-items-center px-1 text-muted-foreground" aria-hidden="true">
      &#8594;
    </div>
  );
}

function TierCard({
  pill, n, what, children, dashed, href,
}: {
  pill: string; n: string; what: string; children: React.ReactNode; dashed?: boolean; href: string;
}) {
  return (
    <Link
      href={href}
      className={
        "block rounded-lg border bg-card p-5 shadow-sm transition-all duration-200 hover:shadow-md hover:-translate-y-0.5 " +
        (dashed ? "border-dashed border-border" : "border-border")
      }
    >
      <span className="inline-block rounded-full border border-border bg-muted px-2.5 py-1 font-mono text-xs font-medium">
        {pill}
      </span>
      <div className="mt-3 text-3xl font-semibold tracking-tight tabular-nums">{n}</div>
      <div className="text-[13px] text-muted-foreground">{what}</div>
      <p className="mt-2.5 text-[13.5px] text-muted-foreground">{children}</p>
      <span className="mt-3 inline-block text-[13px] font-medium">Run it in the demo &#8594;</span>
    </Link>
  );
}

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-secondary text-foreground">
      {/* header: every item is a destination, not an anchor */}
      <header className="sticky top-0 z-20 border-b border-border bg-secondary/85 backdrop-blur">
        <div className="mx-auto flex h-15 max-w-6xl items-center gap-3 px-6 py-3">
          <div className="grid h-8 w-8 shrink-0 place-items-center rounded-sm bg-primary text-primary-foreground text-xs font-semibold">
            T4
          </div>
          <span className="text-base font-semibold tracking-tight">TERE4AI</span>
          <nav aria-label="Main" className="ml-auto flex items-center gap-1 overflow-x-auto">
            <Link href="/assess" className="rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground hover:bg-background hover:text-foreground">
              Assess
            </Link>
            <Link href="/agent" className="rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground hover:bg-background hover:text-foreground">
              Agent replay
            </Link>
            <Link href="/coverage" className="rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground hover:bg-background hover:text-foreground">
              Coverage
            </Link>
            <Link href="/how-it-works" className="rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground hover:bg-background hover:text-foreground">
              How it works
            </Link>
            <Link href="/review" className="rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground hover:bg-background hover:text-foreground">
              Review queue
            </Link>
            <a href={GITHUB} className="rounded-md bg-primary px-3.5 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90">
              GitHub
            </a>
          </nav>
        </div>
      </header>

      <main>
        {/* hero */}
        <section className="mx-auto max-w-6xl px-6 pb-10 pt-20">
          <h1 className="max-w-[17ch] text-balance text-4xl font-semibold leading-[1.08] tracking-[-0.035em] md:text-[52px]">
            The EU AI Act, as a knowledge graph your coding agent can call.
          </h1>
          <p className="mt-5 max-w-[62ch] text-lg leading-relaxed text-muted-foreground">
            TERE4AI is an open-source <strong className="font-medium text-foreground">MCP server</strong> for
            teams building AI systems under Regulation (EU) 2024/1689. A coding agent asks
            what the law requires of the system it is building, and gets back a{" "}
            <strong className="font-medium text-foreground">deterministic risk classification</strong>,
            engineering requirements traced to{" "}
            <strong className="font-medium text-foreground">byte-exact legal text</strong>, judged ethics
            alignments, and{" "}
            <strong className="font-medium text-foreground">requirement-to-code traceability</strong>.
            Models propose; independent judges gate; a rule ladder alone decides.
          </p>
          <div className="mt-7 flex flex-wrap gap-2.5">
            <Link href="/assess" className="rounded-md bg-primary px-4.5 py-2.5 text-sm font-medium text-primary-foreground hover:opacity-90">
              Try the live demo
            </Link>
            <Link href="/agent" className="rounded-md border border-border bg-background px-4.5 py-2.5 text-sm font-medium hover:bg-sidebar">
              Watch an agent use it
            </Link>
            <a href={GITHUB} className="rounded-md border border-border bg-background px-4.5 py-2.5 text-sm font-medium hover:bg-sidebar">
              View on GitHub
            </a>
          </div>
          <div className="mt-9 max-w-2xl rounded-lg border border-border bg-background px-4.5 py-3.5 text-[13.5px] text-muted-foreground">
            <span className="mb-1.5 block text-[11px] font-medium uppercase tracking-[0.05em]">Notice</span>
            {NOTICE}
          </div>
        </section>

        {/* the chain */}
        <section className="mx-auto max-w-6xl px-6 pb-2 pt-4">
          <div className="overflow-x-auto rounded-lg border border-border bg-card p-6 shadow-sm">
            <div className="mb-4 text-[11px] font-medium uppercase tracking-[0.05em] text-muted-foreground">
              One unbroken chain, every answer
            </div>
            <div className="flex min-w-[900px] items-stretch">
              <ChainLink level="Frozen law" value="span:009.001" meta="bytes 727679 to 727924, sha256 3b753e..." />
              <Arrow />
              <ChainLink level="Judged norm" value="norm:eu-ai-act:article-9:paragraph-1:n1" meta="judge: accepted" />
              <Arrow />
              <ChainLink level="Requirement" value="provider shall establish a risk management system" />
              <Arrow />
              <ChainLink level="Ethics" value="hleg:technical-robustness" meta="score 0.798, accepted" />
              <Arrow />
              <ChainLink level="Your code" value="@implements: norm:...article-9..." meta="scoring.py:41" />
            </div>
            <p className="mt-3.5 text-[13px] text-muted-foreground">
              Every hop is machine-checkable in both directions: from a line of code back to
              the exact bytes of the Official Journal snapshot, and from an obligation forward
              to the code that claims to implement it.{" "}
              <Link href="/assess" className="font-medium text-foreground underline underline-offset-2">
                See it live on the assess page.
              </Link>
            </p>
          </div>
        </section>

        {/* five seconds */}
        <section className="mx-auto max-w-6xl px-6 pt-18">
          <div className="text-xs font-medium uppercase tracking-[0.05em] text-muted-foreground">Five seconds</div>
          <h2 className="mt-2 text-balance text-3xl font-semibold tracking-tight">
            What is this, who is it for, what does it do
          </h2>
          <div className="mt-7 grid gap-3 md:grid-cols-3">
            <div className="rounded-lg border border-border bg-card p-5 shadow-sm">
              <h3 className="font-semibold">What it is</h3>
              <p className="mt-2 text-sm text-muted-foreground">
                A knowledge graph of the EU AI Act (113 articles, 180 recitals, 13 annexes,
                parsed deterministically from checksummed official sources) served through the
                Model Context Protocol, so AI coding assistants can query the law the way they
                query a database.
              </p>
            </div>
            <div className="rounded-lg border border-border bg-card p-5 shadow-sm">
              <h3 className="font-semibold">Who it is for</h3>
              <p className="mt-2 text-sm text-muted-foreground">
                Engineers and coding agents building AI systems that must live under the Act,
                and requirements-engineering researchers who need every claim traceable. If
                your agent speaks MCP, it can use TERE4AI today.
              </p>
            </div>
            <div className="rounded-lg border border-border bg-card p-5 shadow-sm">
              <h3 className="font-semibold">What it does</h3>
              <p className="mt-2 text-sm text-muted-foreground">
                Classifies a system&apos;s risk tier by deterministic rules, serves the
                judge-accepted obligations that bind it with citations, maps them to the HLEG
                trustworthy-AI principles, checks which obligations your code claims to
                implement, and generates an audit-grade report.
              </p>
            </div>
          </div>
        </section>

        {/* tiers: each card opens the demo */}
        <section className="mx-auto max-w-6xl px-6 pt-18">
          <div className="text-xs font-medium uppercase tracking-[0.05em] text-muted-foreground">What you get</div>
          <h2 className="mt-2 text-balance text-3xl font-semibold tracking-tight">
            Four honest answers, one per risk tier
          </h2>
          <p className="mt-3 max-w-[62ch] text-muted-foreground">
            The same question, &quot;what does the Act require of this system&quot;, produces
            four very different and equally useful answers. Each card below is a one-click
            scenario on the assess page: the form fills, the deterministic ladder runs live.
          </p>
          <div className="mt-7 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <TierCard pill="minimal_or_none" n="0" what="requirements" href="/assess">
              A citable, rule-traced permission to not build a compliance program. Delete one
              known fact and the system refuses to say it.
            </TierCard>
            <TierCard pill="transparency_only" n="13" what="requirements, Article 50" href="/assess">
              The disclosure and marking duties, each traced to its sentence of the Act, ready
              to close in code and tag.
            </TierCard>
            <TierCard pill="high_risk" n="277" what="requirements, 23 articles" href="/assess">
              The full obligation regime plus the Article 27 fundamental rights impact
              assessment trigger, decided by rule.
            </TierCard>
            <TierCard pill="prohibited" n="0" what="requirements, by design" href="/assess">
              No backlog can make a prohibited practice permissible. The answer is the Article
              5 citation and a full stop.
            </TierCard>
            <TierCard pill="requires_human_review" n="0.5" what="confidence, on purpose" dashed href="/assess">
              When a decisive fact is unknown, the system abstains and names it, rather than
              guessing an exculpating fact into existence.
            </TierCard>
            <Link
              href="/agent"
              className="grid place-items-center rounded-lg border border-border bg-sidebar p-5 text-center shadow-sm transition-all duration-200 hover:shadow-md hover:-translate-y-0.5"
            >
              <div>
                <div className="text-sm font-semibold">Prefer to watch?</div>
                <p className="mt-1.5 text-[13.5px] text-muted-foreground">
                  Step through recorded MCP sessions for all four tiers, raw request and
                  envelope side by side.
                </p>
                <span className="mt-2.5 inline-block text-[13px] font-medium">Agent replay &#8594;</span>
              </div>
            </Link>
          </div>
        </section>

        {/* how it works */}
        <section className="mx-auto max-w-6xl px-6 pt-18">
          <div className="text-xs font-medium uppercase tracking-[0.05em] text-muted-foreground">Trust, by construction</div>
          <h2 className="mt-2 text-balance text-3xl font-semibold tracking-tight">
            Models propose. Judges gate. Rules decide.
          </h2>
          <div className="mt-7 grid gap-3 md:grid-cols-2">
            <div className="rounded-lg border border-border bg-card p-5 shadow-sm">
              <h3 className="font-semibold">The pipeline</h3>
              <ol className="mt-3 grid list-decimal gap-2 pl-5 text-sm text-muted-foreground">
                <li>
                  <b className="font-medium text-foreground">Deterministic mirror.</b> The legal
                  structure is parsed from frozen, checksummed official manifestations. No model
                  touches it.
                </li>
                <li>
                  <b className="font-medium text-foreground">Proposed, then judged.</b> Models
                  extract obligations and ethics mappings as proposals; an independent judge
                  accepts, rejects, or routes each to a disclosed human review queue.
                </li>
                <li>
                  <b className="font-medium text-foreground">Rules decide.</b> A deterministic
                  ladder assigns the risk tier from structured facts. Unknown is never treated
                  as false: the system abstains and names what is missing.
                </li>
                <li>
                  <b className="font-medium text-foreground">Everything cited.</b> Every answer
                  carries a calibrated status, confidence, source spans, and a judge verdict.
                </li>
              </ol>
              <Link href="/how-it-works" className="mt-4 inline-block text-sm font-medium underline underline-offset-2">
                The full pipeline, with diagrams &#8594;
              </Link>
            </div>
            <div className="rounded-lg border border-border bg-card p-5 shadow-sm">
              <h3 className="font-semibold">The evidence subgraph</h3>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/landing/evidence-graph.png"
                alt="The evidence subgraph: requirement nodes connected to HLEG ethics principles by judged alignment edges"
                className="mt-3 w-full rounded-sm border border-border"
                loading="lazy"
              />
              <p className="mt-2.5 text-[13px] text-muted-foreground">
                Ethics mappings are reified, scored, judged assertions. Rejected ones stay
                visible as rejected; nothing is laundered into fact.{" "}
                <Link href="/review" className="font-medium text-foreground underline underline-offset-2">
                  The review queue is public.
                </Link>
              </p>
            </div>
          </div>
        </section>

        {/* numbers */}
        <section className="mx-auto max-w-6xl px-6 pt-18">
          <div className="text-xs font-medium uppercase tracking-[0.05em] text-muted-foreground">Measured, not promised</div>
          <h2 className="mt-2 text-balance text-3xl font-semibold tracking-tight">
            Numbers we publish because they held
          </h2>
          <div className="mt-7 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              ["0 / 345", "label flips across repeat runs", "plain LLM: 43, vector RAG: 51"],
              ["434", "obligations judged", "339 accepted, 54 rejected, 41 held for human review"],
              ["620", "ethics alignments judged", "475 accepted, 145 rejected, all disclosed"],
              ["15", "frozen source files, checksummed", "every quote resolves to bytes and a sha256"],
            ].map(([n, l, q]) => (
              <div key={l} className="rounded-lg border border-border bg-card px-5 py-4 shadow-sm">
                <div className="text-[26px] font-semibold tracking-tight tabular-nums">{n}</div>
                <div className="mt-0.5 text-[13.5px]">{l}</div>
                <div className="mt-1 text-xs text-muted-foreground">{q}</div>
              </div>
            ))}
          </div>
          <p className="mt-4 max-w-[70ch] text-sm text-muted-foreground">
            Live counts on the{" "}
            <Link href="/coverage" className="font-medium text-foreground underline underline-offset-2">
              coverage page
            </Link>{" "}
            are served from the published build, never typed into the page; the{" "}
            <Link href="/review" className="font-medium text-foreground underline underline-offset-2">
              review queue
            </Link>{" "}
            lists everything the judges did not accept.
          </p>
        </section>

        {/* get started */}
        <section className="mx-auto max-w-6xl px-6 pb-4 pt-18">
          <div className="text-xs font-medium uppercase tracking-[0.05em] text-muted-foreground">Get started</div>
          <h2 className="mt-2 text-balance text-3xl font-semibold tracking-tight">
            Wire it into your agent in one config block
          </h2>
          <p className="mt-3 max-w-[62ch] text-muted-foreground">
            Classification, requirements, explanations, ethics traces, and the traceability
            matrix are deterministic and free: no API key needed. Keys unlock the two
            generative tools, both gated by an independent judge.
          </p>
          <pre className="mt-5 overflow-x-auto rounded-lg bg-primary p-5 font-mono text-[13px] leading-relaxed text-primary-foreground/85">
{`// .mcp.json in your project
{
  "mcpServers": {
    "tere4ai": { "command": "python", "args": ["-m", "tere4ai.mcp_server.server"] }
  }
}

# then, from your agent
classify_ai_system(features)      # deterministic tier + rule trace + FRIA
get_applicable_requirements(...)  # judge-accepted obligations, cited
trace_implementation(...)         # which obligations your code claims

# and when you are done
python -m tere4ai.report session.jsonl -o report.html`}
          </pre>
          <div className="mt-5 flex flex-wrap gap-2.5">
            <a href={GITHUB} className="rounded-md bg-primary px-4.5 py-2.5 text-sm font-medium text-primary-foreground hover:opacity-90">
              Read the code
            </a>
            <Link href="/assess" className="rounded-md border border-border bg-background px-4.5 py-2.5 text-sm font-medium hover:bg-sidebar">
              Or just click through the demo
            </Link>
          </div>
        </section>
      </main>

      <footer className="mt-20 border-t border-border bg-sidebar">
        <div className="mx-auto grid max-w-6xl gap-2.5 px-6 py-8 text-[13.5px] text-muted-foreground">
          <p>
            TERE4AI is research software from{" "}
            <a href="https://www.tuni.fi/en" className="font-medium text-foreground hover:underline">
              Tampere University
            </a>
            , published at REFSQ 2026 (
            <a
              href={`${GITHUB}/releases/tag/v1.0-refsq2026`}
              className="font-medium text-foreground hover:underline"
            >
              v1 release and citation
            </a>
            ).
          </p>
          <p>
            Code AGPL-3.0-or-later. Graph metadata CC BY 4.0. EU legal texts under EU reuse
            terms, quoted byte-exact and never altered.
          </p>
          <p>{NOTICE}</p>
        </div>
      </footer>
    </div>
  );
}
