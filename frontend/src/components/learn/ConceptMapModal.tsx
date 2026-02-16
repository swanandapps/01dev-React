import { useEffect, useRef, useState } from "react";
import {
  forceSimulation,
  forceManyBody,
  forceLink,
  forceCenter,
  forceCollide,
  type Simulation,
} from "d3-force";
import { X, Loader2, Network } from "lucide-react";
import { getConceptMap } from "../../lib/learnApi";
import type { Course, ConceptMap, MasteryLevel } from "../../types/learn";

const W = 760;
const H = 520;

const LEVEL: Record<MasteryLevel, { fill: string; stroke: string; label: string }> = {
  mastered: { fill: "#10b981", stroke: "#34d399", label: "Mastered" },
  learning: { fill: "#f59e0b", stroke: "#fbbf24", label: "Learning" },
  weak: { fill: "#f43f5e", stroke: "#fb7185", label: "Needs work" },
  new: { fill: "#52525b", stroke: "#71717a", label: "Not started" },
};

interface SimNode {
  id: string;
  level: MasteryLevel;
  description: string;
  accuracy: number;
  attempts: number;
  x?: number;
  y?: number;
  fx?: number | null;
  fy?: number | null;
}
interface SimLink {
  source: SimNode | string;
  target: SimNode | string;
  type: string;
}

export function ConceptMapModal({
  course,
  userId,
  onClose,
}: {
  course: Course;
  userId: string;
  onClose: () => void;
}) {
  const [map, setMap] = useState<ConceptMap | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [, setTick] = useState(0); // force re-render on each simulation tick
  const [selected, setSelected] = useState<SimNode | null>(null);
  const [hover, setHover] = useState<string | null>(null);

  const nodesRef = useRef<SimNode[]>([]);
  const linksRef = useRef<SimLink[]>([]);
  const simRef = useRef<Simulation<SimNode, undefined> | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const dragId = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getConceptMap(course.course_id, userId)
      .then((m) => {
        if (cancelled) return;
        setMap(m);
        const nodes: SimNode[] = m.concepts.map((c) => ({
          id: c.name,
          level: c.level,
          description: c.description,
          accuracy: c.accuracy,
          attempts: c.attempts,
        }));
        const ids = new Set(nodes.map((n) => n.id));
        const links: SimLink[] = m.relationships
          .filter((r) => ids.has(r.source) && ids.has(r.target))
          .map((r) => ({ source: r.source, target: r.target, type: r.type }));
        nodesRef.current = nodes;
        linksRef.current = links;

        const sim = forceSimulation<SimNode>(nodes)
          .force("charge", forceManyBody().strength(-520))
          .force("link", forceLink<SimNode, SimLink>(links).id((d) => d.id).distance(150))
          .force("center", forceCenter(W / 2, H / 2))
          .force("collide", forceCollide(54))
          .on("tick", () => setTick((t) => t + 1));
        simRef.current = sim;
      })
      .catch((e) => !cancelled && setError((e as Error).message));

    return () => {
      cancelled = true;
      simRef.current?.stop();
    };
  }, [course.course_id, userId]);

  // Convert a pointer event to SVG coordinates.
  const toSvg = (e: React.PointerEvent) => {
    const svg = svgRef.current!;
    const pt = svg.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    const loc = pt.matrixTransform(svg.getScreenCTM()!.inverse());
    return { x: loc.x, y: loc.y };
  };

  const onNodeDown = (e: React.PointerEvent, n: SimNode) => {
    (e.target as Element).setPointerCapture(e.pointerId);
    dragId.current = n.id;
    simRef.current?.alphaTarget(0.3).restart();
    const { x, y } = toSvg(e);
    n.fx = x;
    n.fy = y;
  };
  const onMove = (e: React.PointerEvent) => {
    if (!dragId.current) return;
    const n = nodesRef.current.find((x) => x.id === dragId.current);
    if (!n) return;
    const { x, y } = toSvg(e);
    n.fx = x;
    n.fy = y;
  };
  const onUp = () => {
    if (!dragId.current) return;
    const n = nodesRef.current.find((x) => x.id === dragId.current);
    if (n) {
      n.fx = null;
      n.fy = null;
    }
    dragId.current = null;
    simRef.current?.alphaTarget(0);
  };

  const nodes = nodesRef.current;
  const links = linksRef.current;
  const neighbors = (id: string) =>
    new Set(
      links
        .filter((l) => (l.source as SimNode).id === id || (l.target as SimNode).id === id)
        .flatMap((l) => [(l.source as SimNode).id, (l.target as SimNode).id]),
    );
  const hl = hover ? neighbors(hover) : null;

  return (
    <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-zinc-900 border border-zinc-700 rounded-2xl w-full max-w-4xl flex flex-col max-h-[90vh]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800 flex-shrink-0">
          <div className="flex items-center gap-2">
            <Network className="w-4 h-4 text-indigo-400" />
            <div>
              <h2 className="text-sm font-semibold text-zinc-100">Concept Map</h2>
              <p className="text-xs text-zinc-500">{course.title} · your mastery overlaid</p>
            </div>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 min-h-0 flex flex-col md:flex-row">
          {/* Graph */}
          <div className="flex-1 min-h-0 relative">
            {!map && !error && (
              <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
                <Loader2 className="w-8 h-8 text-indigo-400 animate-spin mb-3" />
                <p className="text-sm text-zinc-300">Building your concept map…</p>
              </div>
            )}
            {error && (
              <div className="absolute inset-0 flex items-center justify-center px-6">
                <p className="text-sm text-amber-300">{error}</p>
              </div>
            )}
            {map && (
              <svg
                ref={svgRef}
                viewBox={`0 0 ${W} ${H}`}
                className="w-full h-full touch-none"
                onPointerMove={onMove}
                onPointerUp={onUp}
                onPointerLeave={onUp}
              >
                <defs>
                  <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                    <path d="M0,0 L10,5 L0,10 z" fill="#818cf8" />
                  </marker>
                </defs>

                {/* edges */}
                {links.map((l, i) => {
                  const s = l.source as SimNode;
                  const t = l.target as SimNode;
                  if (s.x == null || t.x == null) return null;
                  const isPrereq = l.type === "prerequisite_of";
                  const dim = hl && !(hl.has(s.id) && hl.has(t.id));
                  return (
                    <line
                      key={i}
                      x1={s.x}
                      y1={s.y}
                      x2={t.x}
                      y2={t.y}
                      stroke={isPrereq ? "#6366f1" : "#3f3f46"}
                      strokeWidth={isPrereq ? 2 : 1.5}
                      strokeDasharray={l.type === "related_to" ? "4 4" : undefined}
                      markerEnd={isPrereq ? "url(#arrow)" : undefined}
                      opacity={dim ? 0.12 : 0.9}
                    />
                  );
                })}

                {/* nodes */}
                {nodes.map((n) => {
                  if (n.x == null) return null;
                  const col = LEVEL[n.level];
                  const dim = hl && !hl.has(n.id);
                  const r = 26;
                  return (
                    <g
                      key={n.id}
                      transform={`translate(${n.x},${n.y})`}
                      opacity={dim ? 0.25 : 1}
                      className="cursor-pointer"
                      onPointerDown={(e) => onNodeDown(e, n)}
                      onPointerEnter={() => setHover(n.id)}
                      onPointerLeave={() => setHover(null)}
                      onClick={() => setSelected(n)}
                    >
                      <circle r={r} fill={col.fill} fillOpacity={0.25} stroke={col.stroke} strokeWidth={2} />
                      {n.attempts > 0 && (
                        <circle r={r} fill="none" stroke={col.stroke} strokeWidth={3}
                          strokeDasharray={`${Math.max(n.accuracy, 0.02) * 2 * Math.PI * r} ${2 * Math.PI * r}`}
                          transform="rotate(-90)" />
                      )}
                      <text textAnchor="middle" y={r + 14} fontSize="11" fill="#e4e4e7" className="select-none pointer-events-none">
                        {n.id.length > 22 ? n.id.slice(0, 20) + "…" : n.id}
                      </text>
                    </g>
                  );
                })}
              </svg>
            )}
          </div>

          {/* Side panel */}
          <div className="md:w-64 border-t md:border-t-0 md:border-l border-zinc-800 p-4 flex-shrink-0 overflow-y-auto">
            {selected ? (
              <div>
                <span
                  className="inline-block text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full mb-2"
                  style={{ color: LEVEL[selected.level].stroke, background: LEVEL[selected.level].fill + "22" }}
                >
                  {LEVEL[selected.level].label}
                  {selected.attempts > 0 ? ` · ${Math.round(selected.accuracy * 100)}%` : ""}
                </span>
                <h3 className="text-sm font-semibold text-zinc-100 mb-1.5">{selected.id}</h3>
                <p className="text-xs text-zinc-400 leading-relaxed">{selected.description || "No description."}</p>
              </div>
            ) : (
              <p className="text-xs text-zinc-500">Tap a concept to see details. Drag nodes to rearrange.</p>
            )}

            <div className="mt-5 pt-4 border-t border-zinc-800 space-y-1.5">
              {(Object.keys(LEVEL) as MasteryLevel[]).map((k) => (
                <div key={k} className="flex items-center gap-2">
                  <span className="w-3 h-3 rounded-full" style={{ background: LEVEL[k].fill, outline: `1px solid ${LEVEL[k].stroke}` }} />
                  <span className="text-xs text-zinc-400">{LEVEL[k].label}</span>
                </div>
              ))}
              <p className="text-[10px] text-zinc-600 pt-1">→ arrow = prerequisite · dashed = related</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
