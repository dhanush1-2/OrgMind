import { useEffect, useRef, useState } from "react";
import * as d3 from "d3";
import { get } from "../api";
import { Loader2, AlertCircle } from "lucide-react";

interface GraphNode {
  id: string;
  label: string;
  type: string;
  stale?: boolean;
}

interface GraphEdge {
  source: string;
  target: string;
  type: string;
}

interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export default function GraphPage() {
  const svgRef = useRef<SVGSVGElement>(null);
  const [data, setData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<GraphNode | null>(null);

  useEffect(() => {
    get<GraphData>("/graph")
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!data || !svgRef.current) return;

    const el = svgRef.current;
    const W = el.clientWidth || 900;
    const H = el.clientHeight || 600;

    d3.select(el).selectAll("*").remove();

    const svg = d3.select(el)
      .attr("viewBox", `0 0 ${W} ${H}`)
      .call(
        d3.zoom<SVGSVGElement, unknown>().on("zoom", (ev) =>
          g.attr("transform", ev.transform)
        )
      );

    const g = svg.append("g");

    type SimNode = d3.SimulationNodeDatum & GraphNode;
    type SimLink = d3.SimulationLinkDatum<SimNode> & { type: string };

    const nodes: SimNode[] = data.nodes.map((n) => ({ ...n }));
    const nodeById = new Map(nodes.map((n) => [n.id, n]));

    const links: SimLink[] = data.edges
      .map((e) => ({
        source: nodeById.get(e.source) ?? e.source,
        target: nodeById.get(e.target) ?? e.target,
        type: e.type,
      }))
      .filter(
        (l) => typeof l.source === "object" && typeof l.target === "object"
      );

    const sim = d3
      .forceSimulation<SimNode>(nodes)
      .force("link", d3.forceLink<SimNode, SimLink>(links).id((d) => d.id).distance(80))
      .force("charge", d3.forceManyBody().strength(-200))
      .force("center", d3.forceCenter(W / 2, H / 2))
      .force("collision", d3.forceCollide(24));

    const linkEl = g
      .append("g")
      .selectAll("line")
      .data(links)
      .join("line")
      .attr("stroke", (d) => (d.type === "CONFLICTS_WITH" ? "#f59e0b" : "#374151"))
      .attr("stroke-width", 1.5)
      .attr("stroke-dasharray", (d) =>
        d.type === "CONFLICTS_WITH" ? "4,3" : "none"
      );

    const COLOR: Record<string, string> = {
      Decision: "#6366f1",
      Entity: "#10b981",
      Person: "#f59e0b",
    };

    const nodeEl = g
      .append("g")
      .selectAll("circle")
      .data(nodes)
      .join("circle")
      .attr("r", (d) => (d.type === "Decision" ? 10 : 6))
      .attr("fill", (d) => COLOR[d.type] ?? "#6b7280")
      .attr("opacity", (d) => (d.stale ? 0.4 : 1))
      .attr("cursor", "pointer")
      .call(
        d3
          .drag<SVGCircleElement, SimNode>()
          .on("start", (ev, d) => {
            if (!ev.active) sim.alphaTarget(0.3).restart();
            d.fx = d.x; d.fy = d.y;
          })
          .on("drag", (ev, d) => { d.fx = ev.x; d.fy = ev.y; })
          .on("end", (ev, d) => {
            if (!ev.active) sim.alphaTarget(0);
            d.fx = null; d.fy = null;
          }) as unknown as (sel: d3.Selection<SVGCircleElement | d3.BaseType, SimNode, SVGGElement, unknown>) => void
      )
      .on("click", (_, d) => setSelected(d));

    const labelEl = g
      .append("g")
      .selectAll("text")
      .data(nodes)
      .join("text")
      .text((d) => (d.label?.length > 20 ? d.label.slice(0, 20) + "…" : d.label))
      .attr("font-size", 9)
      .attr("fill", "#9ca3af")
      .attr("dy", -12)
      .attr("text-anchor", "middle");

    sim.on("tick", () => {
      linkEl
        .attr("x1", (d) => (d.source as SimNode).x ?? 0)
        .attr("y1", (d) => (d.source as SimNode).y ?? 0)
        .attr("x2", (d) => (d.target as SimNode).x ?? 0)
        .attr("y2", (d) => (d.target as SimNode).y ?? 0);
      nodeEl.attr("cx", (d) => d.x ?? 0).attr("cy", (d) => d.y ?? 0);
      labelEl.attr("x", (d) => d.x ?? 0).attr("y", (d) => d.y ?? 0);
    });

    return () => { sim.stop(); };
  }, [data]);

  if (loading)
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="animate-spin text-indigo-400" size={32} />
      </div>
    );

  if (error)
    return (
      <div className="p-8 text-red-400">
        <AlertCircle className="inline mr-2" size={16} />
        {error}
      </div>
    );

  return (
    <div className="flex flex-col h-full">
      <div className="px-8 py-5 border-b border-gray-800 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Knowledge Graph</h1>
          <p className="text-sm text-gray-400">
            {data?.nodes.length} nodes · {data?.edges.length} edges
          </p>
        </div>
        <div className="flex gap-4 text-xs text-gray-500">
          <span><span className="inline-block w-2 h-2 rounded-full bg-indigo-500 mr-1" />Decision</span>
          <span><span className="inline-block w-2 h-2 rounded-full bg-emerald-500 mr-1" />Entity</span>
          <span><span className="inline-block w-2 h-2 rounded-full bg-yellow-500 mr-1" />Person</span>
        </div>
      </div>

      <div className="relative flex-1">
        <svg ref={svgRef} className="w-full h-full" />
        {selected && (
          <div className="absolute top-4 right-4 bg-gray-800 border border-gray-700 rounded-xl p-4 w-56 text-sm">
            <p className="font-medium text-gray-100 mb-1">{selected.label}</p>
            <p className="text-gray-500 text-xs">{selected.type}</p>
            {selected.stale && (
              <p className="text-yellow-500 text-xs mt-1">⚠ Stale</p>
            )}
            <button
              className="mt-2 text-gray-600 hover:text-gray-400 text-xs"
              onClick={() => setSelected(null)}
            >
              Dismiss
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
