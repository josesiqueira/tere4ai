import fs from "node:fs";
import path from "node:path";

/* Reader for public/mcp-demo/index.json, which scripts/build_mcp_demo_index.py
   derives from the recorded MCP sessions in demo/mcp_demo/sessions. Every
   figure the MCP demo pages render comes from this file, and every value in
   this file was copied out of a recorded envelope, so no page can state a
   number the server did not answer. The read is guarded: the index is a
   generated artifact, and a checkout that has not run the build script must
   see an honest setup notice rather than a fabricated zero. */

export type Claim = {
  line: number | null;
  norm_id: string | null;
  article: string | null;
  source_span_id: string | null;
  accepted: boolean;
  refusal_reason?: string | null;
  modal: string | null;
  action: string | null;
  object: string | null;
};

export type CodeFile = { path: string; claims: Claim[] };

export type DemoSystem = {
  key: string;
  product: string;
  label: string;
  blurb: string;
  report: string;
  session_file: string;
  repo_ref: string | null;
  exchanges: { seq: number; tool: string; status: string | null }[];
  classification: {
    risk_category: string | null;
    prohibited: boolean | null;
    status: string | null;
    confidence: number | null;
    rationale: string[];
    source_nodes: string[];
    missing_facts: string[];
    fria: string | null;
  };
  requirements: {
    returned: number | null;
    total_accepted_in_scope: number | null;
    needs_human_review_total: number | null;
    articles: number;
    message: string | null;
    per_article: Record<string, { accepted: number; needs_human_review: number }>;
  };
  trace: {
    applicable_norms: number | null;
    traced: number | null;
    untraced: number | null;
    invalid_tags: number | null;
    tag_convention: string | null;
    trace_note: string | null;
    code_index: CodeFile[];
  } | null;
};

export type DemoIndex = {
  graph_versions: string[];
  non_legal_advice_notice: string | null;
  systems: DemoSystem[];
};

export function loadDemoIndex(): DemoIndex | null {
  const p = path.join(process.cwd(), "public", "mcp-demo", "index.json");
  try {
    return JSON.parse(fs.readFileSync(p, "utf-8"));
  } catch {
    return null;
  }
}

export function findSystem(index: DemoIndex, key: string): DemoSystem | undefined {
  return index.systems.find((s) => s.key === key);
}
