import { useRef, useState, useEffect } from "react";
import Header from "../components/Home/Header";

interface Article {
  id: number;
  title: string;
  description: string;
  x: number;
  y: number;
  color: string;
}

const ARTICLES: Article[] = [
  { id: 1, title: "V8 Hidden Classes", description: "How V8 optimizes object property access", x: 200, y: 150, color: "border-sky-500" },
  { id: 2, title: "Prototype Chain", description: "JavaScript's inheritance mechanism", x: 500, y: 300, color: "border-red-500" },
  { id: 3, title: "Event Loop", description: "The heart of Node.js asynchrony", x: 850, y: 180, color: "border-green-500" },
  { id: 4, title: "WebSocket Protocol", description: "Full-duplex browser communication", x: 300, y: 500, color: "border-purple-500" },
  { id: 5, title: "ES Modules", description: "The native JavaScript module system", x: 700, y: 450, color: "border-orange-500" },
  { id: 6, title: "JIT Compilation", description: "How V8 makes JavaScript fast", x: 1100, y: 350, color: "border-pink-500" },
  { id: 7, title: "Memory Management", description: "Garbage collection in V8", x: 600, y: 650, color: "border-yellow-500" },
  { id: 8, title: "TCP Sockets", description: "Low-level network communication", x: 150, y: 700, color: "border-blue-500" },
];

export default function MapsPage() {
  const canvasRef = useRef<HTMLDivElement>(null);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);

  const handleMouseDown = (e: React.MouseEvent) => {
    setDragging(true);
    setDragStart({ x: e.clientX - offset.x, y: e.clientY - offset.y });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!dragging) return;
    setOffset({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y });
  };

  const handleMouseUp = () => setDragging(false);

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    setZoom((z) => Math.min(Math.max(z * delta, 0.3), 3));
  };

  useEffect(() => {
    const el = canvasRef.current;
    if (!el) return;
    const handler = (e: WheelEvent) => e.preventDefault();
    el.addEventListener("wheel", handler, { passive: false });
    return () => el.removeEventListener("wheel", handler);
  }, []);

  return (
    <div className="bg-zinc-950 text-[#F0F0F0] min-h-screen overflow-hidden">
      <Header />
      <div className="pt-16 h-screen flex flex-col">
        <div className="px-6 py-4 border-b border-zinc-800 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-white">Knowledge Map</h1>
            <p className="text-zinc-500 text-xs">Drag to explore · Scroll to zoom</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setZoom((z) => Math.min(z * 1.2, 3))}
              className="bg-zinc-800 text-white w-8 h-8 rounded-lg text-lg hover:bg-zinc-700"
            >
              +
            </button>
            <button
              onClick={() => setZoom((z) => Math.max(z * 0.8, 0.3))}
              className="bg-zinc-800 text-white w-8 h-8 rounded-lg text-lg hover:bg-zinc-700"
            >
              -
            </button>
            <button
              onClick={() => { setOffset({ x: 0, y: 0 }); setZoom(1); }}
              className="bg-zinc-800 text-zinc-400 px-3 h-8 rounded-lg text-xs hover:bg-zinc-700"
            >
              Reset
            </button>
          </div>
        </div>

        <div
          ref={canvasRef}
          className="flex-1 overflow-hidden cursor-grab active:cursor-grabbing select-none"
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          onWheel={handleWheel}
        >
          <div
            style={{
              transform: `translate(${offset.x}px, ${offset.y}px) scale(${zoom})`,
              transformOrigin: "0 0",
              width: "1400px",
              height: "900px",
              position: "relative",
            }}
          >
            <svg
              className="absolute inset-0 pointer-events-none"
              width="1400"
              height="900"
            >
              {ARTICLES.map((a, i) =>
                ARTICLES.slice(i + 1).map((b) => {
                  const dist = Math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2);
                  if (dist > 500) return null;
                  return (
                    <line
                      key={`${a.id}-${b.id}`}
                      x1={a.x + 80}
                      y1={a.y + 40}
                      x2={b.x + 80}
                      y2={b.y + 40}
                      stroke="#27272a"
                      strokeWidth="1"
                    />
                  );
                })
              )}
            </svg>

            {ARTICLES.map((article) => (
              <div
                key={article.id}
                className={`absolute bg-zinc-900 border-2 ${article.color} rounded-xl p-4 w-44 cursor-pointer hover:scale-105 transition-transform hover:z-10`}
                style={{ left: article.x, top: article.y }}
                onClick={(e) => e.stopPropagation()}
              >
                <h3 className="text-white text-sm font-semibold mb-1">{article.title}</h3>
                <p className="text-zinc-500 text-xs leading-relaxed">{article.description}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
