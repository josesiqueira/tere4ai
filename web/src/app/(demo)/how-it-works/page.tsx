"use client";

/* How TERE4AI works: the trust split, the judges, and the calibrated
   vocabulary. Reads the status vocabulary live from the facade's
   .well-known so this page cannot drift from server truth. The facade is
   reached the same way web/src/app/assess/page.tsx reaches it: the shared
   FACADE_URL constant from @/lib/facade, never same-origin (the demo UI is
   a thin client over a separately hosted facade, docs/architecture.md
   Section 9). */

import { useEffect, useState } from "react";

import { FACADE_URL } from "@/lib/facade";
import { VOCAB_SUBTITLES } from "@/lib/vocab";

type WellKnown = {
  status_vocabulary?: string[];
  endpoints?: Record<string, { method: string; path: string; paid: boolean }>;
};

/* Loading placeholder for the vocabulary grid: a skeleton, not a spinner,
   so the section keeps its final shape while the fetch is in flight. */
function VocabSkeleton() {
  return (
    <ul className="grid grid-cols-1 gap-3 md:grid-cols-2" aria-hidden="true">
      {Array.from({ length: 7 }).map((_, i) => (
        <li key={i} className="rounded-md border p-3">
          <div className="h-3 w-2/5 animate-pulse rounded bg-muted" />
          <div className="mt-2 h-3 w-4/5 animate-pulse rounded bg-muted" />
        </li>
      ))}
    </ul>
  );
}

export default function HowItWorksPage() {
  const [wk, setWk] = useState<WellKnown | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${FACADE_URL}/.well-known/tere4ai.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then(setWk)
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mx-auto max-w-4xl space-y-8">
        <header className="space-y-2">
          <h1 className="text-2xl font-semibold">How it works</h1>
          <p className="text-sm leading-6 text-muted-foreground">
            TERE4AI answers questions about the EU AI Act with evidence, not
            opinions. A deterministic parser mirrors the frozen legal text
            into a knowledge graph; language models only propose norms,
            mappings, and facts; independent judges gate every proposal; and
            a fixed rule ladder alone decides risk classification. No model
            ever overrides the rules.
          </p>
        </header>

        <section className="space-y-3" aria-labelledby="architecture-heading">
          <h2 id="architecture-heading" className="text-xl font-semibold">
            Architecture
          </h2>
          <img
            src="/tere4ai_v2_architecture.svg"
            alt="TERE4AI v2 architecture: frozen sources, deterministic parser, knowledge graph, judged pipelines, MCP server and facade"
            className="w-full rounded-lg border bg-card p-2"
          />
        </section>

        <section className="space-y-3" aria-labelledby="judges-heading">
          <h2 id="judges-heading" className="text-xl font-semibold">
            The judge pipeline
          </h2>
          <img
            src="/judge_diagram.svg"
            alt="Judge pipeline: generator proposals gated by build-time extraction and mapping judges and a runtime grounding judge from an independent model family"
            className="w-full rounded-lg border bg-card p-2"
          />
          <p className="text-sm leading-6 text-muted-foreground">
            The generator and the judges run on independent model families,
            because correlated failure modes would weaken the control. Every
            judged decision is logged with its prompt hash.
          </p>
        </section>

        <section className="space-y-3" aria-labelledby="vocabulary-heading">
          <h2 id="vocabulary-heading" className="text-xl font-semibold">
            Calibrated vocabulary
          </h2>
          <p className="text-sm leading-6 text-muted-foreground">
            Every answer carries one of these statuses, served live from the
            running facade. Stronger claims are structurally impossible.
          </p>
          {error ? (
            <p role="alert" className="text-sm text-destructive">
              Vocabulary unavailable (facade offline): {error}
            </p>
          ) : wk ? (
            <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {(wk.status_vocabulary ?? []).map((s) => (
                <li key={s} className="rounded-md border p-3">
                  <code className="font-mono text-xs">{s}</code>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {VOCAB_SUBTITLES[s] ?? "see architecture.md Section 8"}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <VocabSkeleton />
          )}
        </section>

        <footer className="border-t pt-4 text-xs text-muted-foreground">
          TERE4AI provides engineering and documentation support. It does not
          certify anything and does not replace legal review, conformity
          assessment, or competent-authority interpretation. EU to HLEG
          mappings are LLM-generated and not expert-validated.
        </footer>
      </div>
    </div>
  );
}
