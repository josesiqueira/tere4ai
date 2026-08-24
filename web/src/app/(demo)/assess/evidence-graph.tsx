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

/* Node ids share long, identical prefixes ("norm:eu-ai-act:article-9:..."),
   so truncating the raw id from the left rendered every label in an article
   group as the same unreadable stub ("article-9:paragraph-5…"). Structural
   ids are rendered as the citation a lawyer would write instead, which is
   both shorter and the form the rest of the UI already speaks; anything that
   does not parse falls back to the prefix-stripped id rather than being
   guessed at. The full id always remains in the node's <title> and
   aria-label, so this shortens the label without hiding anything. */
function truncateLabel(id: string, max = 22): string {
  const body = id.replace(/^(norm:|align:)/, "").replace(/^eu-ai-act:/, "");

  const article = /^article-(\d+[a-z]?)(.*)$/.exec(body);
  if (article) {
    const [, number, rest] = article;
    return `Art. ${number}${subdivisions(rest)}`;
  }

  const annex = /^annex-([ivx]+)(.*)$/.exec(body);
  if (annex) {
    const [, numeral, rest] = annex;
    return `Annex ${numeral.toUpperCase()}${subdivisions(rest)}`;
  }

  const short = body.replace(/^(hleg:|altai:)/, "");
  return short.length > max ? `${short.slice(0, max - 1)}…` : short;
}

/* ":paragraph-5:point-a:n1" renders as "(5)(a) n1". The trailing nN is the
   norm's index within its provision, kept because one provision routinely
   yields several distinct normative statements. */
function subdivisions(rest: string): string {
  let out = "";
  for (const [, value] of rest.matchAll(/:(?:paragraph|point|subpoint)-([\w-]+)/g)) {
    out += `(${value})`;
  }
  const normIndex = /:(n\d+)$/.exec(rest);
  if (normIndex) out += ` ${normIndex[1]}`;
  return out;
}

/* The canvas is a LOGICAL coordinate space, not a pixel size: the SVG carries
   a viewBox and no width attribute, so it always scales to the frame it is
   rendered into. These constants therefore set the graph's aspect ratio and
   how much room the force layout has to separate nodes, and nothing here
   depends on measuring the DOM (an earlier attempt did, and a collapsed
   accordion measuring zero pinned the layout to a stale width). */
const MIN_WIDTH = 560;
const MAX_WIDTH = 1100;
const NODE_R = 15;

/* Denser graphs need vertical room, otherwise forceCollide packs 25 nodes
   into one flat band and the labels sit on top of each other. */
function frameHeight(nodeCount: number): number {
  if (nodeCount > 18) return 460;
  if (nodeCount > 10) return 380;
  return 300;
}

type SimNode = SimulationNodeDatum & { id: string; layer: Layer };
type SimLink = SimulationLinkDatum<SimNode> & GraphEvidenceEdge;

/* Runs forceLink + forceManyBody + forceCenter synchronously (tick loop,
   no requestAnimationFrame) and returns settled positions once. */
function layoutGraph(
  nodeIds: string[],
  edges: GraphEvidenceEdge[]
): { nodes: SimNode[]; links: SimLink[]; viewBox: string } {
  const nodes: SimNode[] = nodeIds.map((id) => ({ id, layer: inferLayer(id) }));
  const known = new Set(nodeIds);
  const links: SimLink[] = edges
    .filter((e) => known.has(e.from) && known.has(e.to))
    .map((e) => ({ ...e, source: e.from, target: e.to }));

  /* Grows with the node count so a busy graph gets room to spread, but caps
     well below the old 1400: that cap, combined with a fixed pixel width,
     drew the cluster centred at 700 half outside a ~900px column, leaving
     the reader to scroll sideways to find it. */
  const width = Math.max(MIN_WIDTH, Math.min(nodeIds.length * 100, MAX_WIDTH));
  const height = frameHeight(nodeIds.length);

  const simulation = forceSimulation(nodes)
    .force(
      "link",
      forceLink<SimNode, SimLink>(links)
        .id((d) => d.id)
        .distance(90)
        .strength(0.5)
    )
    .force("charge", forceManyBody().strength(-260))
    .force("center", forceCenter(width / 2, height / 2))
    .force("collide", forceCollide(NODE_R + 14))
    .stop();

  for (let i = 0; i < 250; i += 1) simulation.tick();

  // Clamp into the visible frame so labels are never clipped at the edges.
  const pad = NODE_R + 24;
  for (const n of nodes) {
    n.x = Math.min(width - pad, Math.max(pad, n.x ?? width / 2));
    n.y = Math.min(height - pad, Math.max(pad, n.y ?? height / 2));
  }

  /* The settled cluster rarely fills the canvas it was laid out on, so frame
     the viewBox on the nodes themselves. Without this the graph renders as a
     small island inside wide empty margins. The horizontal padding leaves
     room for the centred labels, which are wider than their nodes. */
  const xs = nodes.map((n) => n.x ?? 0);
  const ys = nodes.map((n) => n.y ?? 0);
  const padX = 70;
  const padY = 34;
  const minX = Math.min(...xs) - padX;
  const minY = Math.min(...ys) - padY;
  const viewWidth = Math.max(Math.max(...xs) + padX - minX, 200);
  const viewHeight = Math.max(Math.max(...ys) + padY - minY, 160);

  return { nodes, links, viewBox: `${minX} ${minY} ${viewWidth} ${viewHeight}` };
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
          <div>
            {/* No width attribute on purpose: the viewBox scales the graph to
                whatever width the frame has, at any window size and in any
                accordion state, so it can never be clipped out of view. The
                height cap stops a dense graph pushing the rest of the
                requirement off the screen; when it binds, the viewBox
                letterboxes rather than crops. */}
            <svg
              viewBox={layout.viewBox}
              preserveAspectRatio="xMidYMid meet"
              role="img"
              aria-label="Evidence subgraph: legal, normative, and ethics nodes with their alignment edges"
              className="block w-full h-auto max-h-[520px]"
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
