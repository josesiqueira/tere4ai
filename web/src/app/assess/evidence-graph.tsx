"use client";

/* Evidence subgraph viewer (Demo revamp C, task 4). Renders
   envelope.graph_evidence_subgraph as a small force-directed graph.

   DATA SHAPE (verified against the live free tools 2026-07-29, not assumed):
   classify_ai_system and get_applicable_requirements never pass
   graph_evidence_subgraph to make_envelope (src/tere4ai/mcp_server/
   classify.py, requirements.py), so it is always {} for those two answers.
   The free, deterministic trace_alignment and explain_requirement tools
   (src/tere4ai/mcp_server/trace.py, explain.py) DO populate it, as
   { nodes: string[], edges: { from, to, via_assertion?, relation_type?,
   judge_verdict? }[] }. Nodes are bare node id strings; there is no
   per-node layer or type field anywhere in this payload. This component
   therefore infers a display layer from the id's own naming convention
   (docs/architecture.md Section 1 layer list, Section 2 ELI-like ids):
   "norm:" prefix is a Layer 2 NormativeStatement, "hleg:" (or "altai:") is
   a Layer 3 ethics node, "align:" is a Layer 3 alignment assertion id
   (only ever seen as an edge's via_assertion, kept here in case one ever
   appears as a bare node), and everything else (the "eu-ai-act:..." legal
   structure ids) is Layer 1. Anything unrecognised falls into an explicit
   "other" bucket rather than being guessed into one of the above, so the
   legend never claims a category that is not actually grounded in the id.

   d3-force runs synchronously here: the simulation is ticked in a plain
   loop and never re-rendered on a timer, so the SVG is static the moment
   it mounts (no animation loop, per the task brief).

   Colors: DESIGN.md chart-1..5 tokens only, one per inferred layer
   (1 to 4) plus chart-5 for the "other" bucket, via Tailwind's
   fill-chart-N utilities so light/dark follow the CSS variables
   automatically. */

import { useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force";

import { FACADE_URL } from "@/lib/facade";

export type GraphEvidenceEdge = {
  from: string;
  to: string;
  via_assertion?: string;
  relation_type?: string;
  judge_verdict?: string;
};

/* The full envelope.graph_evidence_subgraph field is a union: the empty
   object (classify, requirements, and any degraded answer), the nodes and
   edges shape above (trace_alignment, explain_requirement, evidence,
   backlog, source_trace), or coverage_report's own node/edge COUNT shape
   (node_counts_by_type / edge_counts_by_type), which is an aggregate, not
   a graph, and is never passed to this component. Only the nodes/edges
   shape renders here; anything else is treated as empty. */
export type GraphEvidenceSubgraph = {
  nodes?: string[];
  edges?: GraphEvidenceEdge[];
};

const EMPTY_SUBGRAPH: GraphEvidenceSubgraph = {};

/* Merges any number of per-norm subgraphs (for example one per accepted
   norm in an article group's /api/trace/batch envelopes) into one, deduped
   by node id and by (from, to, via_assertion) edge identity. Never invents
   an edge or node not present in at least one source subgraph. */
export function mergeSubgraphs(
  subgraphs: (GraphEvidenceSubgraph | null | undefined)[]
): GraphEvidenceSubgraph {
  const nodes = new Set<string>();
  const edges: GraphEvidenceEdge[] = [];
  const seenEdges = new Set<string>();
  for (const sub of subgraphs) {
    for (const id of sub?.nodes ?? []) nodes.add(id);
    for (const edge of sub?.edges ?? []) {
      const key = `${edge.from}>${edge.to}>${edge.via_assertion ?? ""}`;
      if (seenEdges.has(key)) continue;
      seenEdges.add(key);
      edges.push(edge);
    }
  }
  return nodes.size > 0 ? { nodes: Array.from(nodes), edges } : {};
}

type Layer = 1 | 2 | 3 | 4 | 5;

const LAYER_FILL: Record<Layer, string> = {
  1: "fill-chart-1",
  2: "fill-chart-2",
  3: "fill-chart-3",
  4: "fill-chart-4",
  5: "fill-chart-5",
};

const LAYER_LABEL: Record<Layer, string> = {
  1: "Legal structure (article, paragraph, annex)",
  2: "Normative statement",
  3: "HLEG / ethics",
  4: "Alignment assertion",
  5: "Other",
};

function inferLayer(nodeId: string): Layer {
  if (nodeId.startsWith("norm:")) return 2;
  if (nodeId.startsWith("hleg:") || nodeId.startsWith("altai:")) return 3;
  if (nodeId.startsWith("align:")) return 4;
  if (nodeId.startsWith("eu-ai-act:")) return 1;
  return 5;
}

function truncateLabel(id: string, max = 22): string {
  return id.length > max ? `${id.slice(0, max - 1)}…` : id;
}

const HEIGHT = 320;
const NODE_R = 15;

type SimNode = SimulationNodeDatum & { id: string; layer: Layer };
type SimLink = SimulationLinkDatum<SimNode> & GraphEvidenceEdge;

/* Runs forceLink + forceManyBody + forceCenter synchronously (tick loop,
   no requestAnimationFrame) and returns settled positions once. */
function layoutGraph(
  nodeIds: string[],
  edges: GraphEvidenceEdge[]
): { nodes: SimNode[]; links: SimLink[]; width: number } {
  const nodes: SimNode[] = nodeIds.map((id) => ({ id, layer: inferLayer(id) }));
  const known = new Set(nodeIds);
  const links: SimLink[] = edges
    .filter((e) => known.has(e.from) && known.has(e.to))
    .map((e) => ({ ...e, source: e.from, target: e.to }));

  const width = Math.min(1400, Math.max(480, nodeIds.length * 100));

  const simulation = forceSimulation(nodes)
    .force(
      "link",
      forceLink<SimNode, SimLink>(links)
        .id((d) => d.id)
        .distance(90)
        .strength(0.5)
    )
    .force("charge", forceManyBody().strength(-260))
    .force("center", forceCenter(width / 2, HEIGHT / 2))
    .force("collide", forceCollide(NODE_R + 14))
    .stop();

  for (let i = 0; i < 250; i += 1) simulation.tick();

  // Clamp into the visible frame so labels are never clipped at the edges.
  const pad = NODE_R + 24;
  for (const n of nodes) {
    n.x = Math.min(width - pad, Math.max(pad, n.x ?? width / 2));
    n.y = Math.min(HEIGHT - pad, Math.max(pad, n.y ?? HEIGHT / 2));
  }

  return { nodes, links, width };
}

type SpanPanelState = {
  nodeId: string;
  loading: boolean;
  error: string | null;
  data: { span_id: string; text: string; snapshot_file: string } | null;
};

const TOGGLE_BUTTON =
  "inline-flex items-center justify-center h-8 px-3 rounded-md border " +
  "border-input bg-transparent shadow-xs text-xs font-medium " +
  "transition-all duration-200 hover:bg-accent";

function SpanChip({ children }: { children: React.ReactNode }) {
  return (
    <code className="rounded-md bg-muted px-1.5 py-0.5 font-mono text-xs break-all">
      {children}
    </code>
  );
}

/* Client component: `<EvidenceGraph subgraph={...} />`. Renders nothing
   when the subgraph carries no nodes (the common case for classify and
   requirements answers), per the task contract: an empty subgraph is
   never padded with invented content. */
export function EvidenceGraph({
  subgraph,
  nodeSpanIds,
}: {
  subgraph: GraphEvidenceSubgraph | null | undefined;
  /* Optional node id -> span id map, supplied by the caller from data it
     already holds (a requirement's own source_span_id, or an alignment
     assertion's evidence span ids). A node with no entry here renders
     without a click affordance: this component never guesses a span id
     for a node, since a wrong guess would be an uncited claim. */
  nodeSpanIds?: Record<string, string>;
}) {
  const [open, setOpen] = useState(false);
  const [panel, setPanel] = useState<SpanPanelState | null>(null);

  const nodeIds = subgraph?.nodes ?? EMPTY_SUBGRAPH.nodes ?? [];
  const edges = useMemo(() => subgraph?.edges ?? [], [subgraph]);
  const nodesKey = nodeIds.join("|");
  const edgesKey = edges.map((e) => `${e.from}>${e.to}>${e.via_assertion ?? ""}`).join("|");

  const layout = useMemo(() => {
    if (nodeIds.length === 0) return null;
    return layoutGraph(nodeIds, edges);
    // nodesKey/edgesKey are stable string digests of nodeIds/edges, used so
    // the simulation only reruns when the actual graph content changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodesKey, edgesKey]);

  if (nodeIds.length === 0 || !layout) return null;

  const layersPresent = Array.from(new Set(layout.nodes.map((n) => n.layer))).sort();

  async function openSpan(nodeId: string, spanId: string) {
    setPanel({ nodeId, loading: true, error: null, data: null });
    try {
      const res = await fetch(`${FACADE_URL}/api/span/${encodeURIComponent(spanId)}`);
      const body = await res.json();
      if (!res.ok) {
        setPanel({
          nodeId,
          loading: false,
          error: typeof body.error === "string" ? body.error : `HTTP ${res.status}`,
          data: null,
        });
        return;
      }
      setPanel({ nodeId, loading: false, error: null, data: body });
    } catch (err) {
      setPanel({
        nodeId,
        loading: false,
        error: err instanceof Error ? err.message : String(err),
        data: null,
      });
    }
  }

  return (
    <div className="space-y-2 border-t border-border p-3">
      <button
        type="button"
        className={TOGGLE_BUTTON}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        {open ? "Hide evidence graph" : "Show evidence graph"} ({layout.nodes.length} nodes,{" "}
        {layout.links.length} edges)
      </button>
      {open && (
        <div className="rounded-md border border-border p-3 space-y-3">
          <div className="overflow-x-auto">
            <svg
              width={layout.width}
              height={HEIGHT}
              viewBox={`0 0 ${layout.width} ${HEIGHT}`}
              role="img"
              aria-label="Evidence subgraph: legal, normative, and ethics nodes with their alignment edges"
              className="block"
            >
              <g>
                {layout.links.map((link, i) => {
                  const source = link.source as SimNode;
                  const target = link.target as SimNode;
                  const accepted =
                    link.judge_verdict === undefined || link.judge_verdict === "accepted";
                  return (
                    <line
                      key={`${link.from}>${link.to}>${i}`}
                      x1={source.x}
                      y1={source.y}
                      x2={target.x}
                      y2={target.y}
                      className="stroke-border"
                      strokeWidth={1.5}
                      strokeDasharray={accepted ? undefined : "4 3"}
                      opacity={accepted ? 0.8 : 0.5}
                    >
                      <title>
                        {[link.relation_type, link.judge_verdict].filter(Boolean).join(" · ") ||
                          `${link.from} → ${link.to}`}
                      </title>
                    </line>
                  );
                })}
              </g>
              <g>
                {layout.nodes.map((node) => {
                  const spanId = nodeSpanIds?.[node.id];
                  const clickable = Boolean(spanId);
                  return (
                    <g
                      key={node.id}
                      transform={`translate(${node.x},${node.y})`}
                      className={clickable ? "cursor-pointer" : undefined}
                      tabIndex={clickable ? 0 : undefined}
                      role={clickable ? "button" : undefined}
                      aria-label={clickable ? `View source span for ${node.id}` : node.id}
                      onClick={clickable ? () => openSpan(node.id, spanId!) : undefined}
                      onKeyDown={
                        clickable
                          ? (e) => {
                              if (e.key === "Enter" || e.key === " ") {
                                e.preventDefault();
                                void openSpan(node.id, spanId!);
                              }
                            }
                          : undefined
                      }
                    >
                      <title>{node.id}</title>
                      <circle
                        r={NODE_R}
                        className={`${LAYER_FILL[node.layer]} stroke-background ${
                          clickable ? "hover:opacity-80" : ""
                        }`}
                        strokeWidth={2}
                      />
                      <text
                        y={NODE_R + 12}
                        textAnchor="middle"
                        className="fill-muted-foreground text-[10px]"
                      >
                        {truncateLabel(node.id)}
                      </text>
                    </g>
                  );
                })}
              </g>
            </svg>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
            {layersPresent.map((layer) => (
              <span key={layer} className="inline-flex items-center gap-1.5">
                <svg width={10} height={10} aria-hidden="true">
                  <circle cx={5} cy={5} r={5} className={LAYER_FILL[layer]} />
                </svg>
                {LAYER_LABEL[layer]}
              </span>
            ))}
          </div>
          {panel && (
            <div className="rounded-md border border-border bg-muted/30 p-3 space-y-2">
              <div className="flex items-start justify-between gap-2">
                <p className="text-xs font-semibold">
                  Source span{" "}
                  <code className="font-mono font-normal text-muted-foreground">
                    {panel.nodeId}
                  </code>
                </p>
                <button
                  type="button"
                  className="text-xs text-muted-foreground hover:text-foreground"
                  onClick={() => setPanel(null)}
                  aria-label="Close source span panel"
                >
                  Close
                </button>
              </div>
              {panel.loading && (
                <p className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
                  Loading verbatim span...
                </p>
              )}
              {panel.error && <p className="text-xs text-destructive">{panel.error}</p>}
              {panel.data && (
                <>
                  <blockquote className="border-l-2 border-border pl-3 text-sm text-muted-foreground">
                    &ldquo;{panel.data.text}&rdquo;
                  </blockquote>
                  <div className="flex flex-wrap gap-1.5">
                    <SpanChip>{panel.data.span_id}</SpanChip>
                    <SpanChip>{panel.data.snapshot_file}</SpanChip>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
