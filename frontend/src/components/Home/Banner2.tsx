import React from "react";
import { Link } from "react-router-dom";

const TESTIMONIALS = [
  { img: "/tweet_anjali.png",      alt: "Anjali Chauhan tweet" },
  { img: "/tweet_palacharla.png",  alt: "Palacharla Narendra tweet" },
  { img: "/tweet_vattsal.png",     alt: "Vattsal Bhatt tweet" },
  { img: "/footerfeedback.jpg",    alt: "Zuhed Shaikh LinkedIn post" },
  { img: "/footerfeedback2.png",   alt: "Vikram K. LinkedIn post" },
];

const FEATURED_TRACKS = [
  {
    id: 2,
    title: "Build a Custom Library",
    tag: "JavaScript Internals",
    desc: "Start with Brendan Eich's Js 1.0, hack the prototype chain, build window-compatible and ES-module-compatible libraries, and ship to NPM.",
    color: "from-red-900/40 to-red-950/60",
    border: "border-red-500/30",
    accent: "text-red-400",
    badge: "bg-red-500/10 text-red-400 border-red-500/20",
    available: true,
  },
  {
    id: 5,
    title: "Build a State Management Library",
    tag: "Reactivity & Internals",
    desc: "JavaScript Proxy, dependency tracking, computed state, time-travel debugging — build the engine that powers Pinia, Redux, and Zustand.",
    color: "from-blue-900/40 to-blue-950/60",
    border: "border-blue-500/30",
    accent: "text-blue-400",
    badge: "bg-blue-500/10 text-blue-400 border-blue-500/20",
    available: false,
  },
  {
    id: 7,
    title: "JavaScript Engine Internals",
    tag: "V8 Deep Dive",
    desc: "Ignition bytecode, TurboFan JIT, hidden classes, garbage collection — crack open V8 and learn to write JavaScript it loves.",
    color: "from-sky-900/40 to-sky-950/60",
    border: "border-sky-500/30",
    accent: "text-sky-400",
    badge: "bg-sky-500/10 text-sky-400 border-sky-500/20",
    available: false,
  },
];

const METHODOLOGY = [
  {
    icon: "⚙️",
    title: "Build, don't memorise",
    desc: "Every concept is learned by implementing it. You won't read about compilers — you'll write one.",
  },
  {
    icon: "🔬",
    title: "Source code first",
    desc: "We read the source of Axios, Pinia, V8, and Express. Real code, not simplified toy examples.",
  },
  {
    icon: "📐",
    title: "First principles only",
    desc: "We start from the bottom: TCP sockets, bytecode, the prototype chain. No hand-waving.",
  },
  {
    icon: "🚀",
    title: "Shippable projects",
    desc: "Every track ends with something real — a published NPM package, a benchmarked framework, a working engine.",
  },
];

export default function Banner2() {
  return (
    <>
      {/* Featured Tracks */}
      <section className="py-24 px-6 bg-zinc-950 border-t border-zinc-900">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-end justify-between mb-12">
            <div>
              <p className="text-indigo-400 text-sm font-semibold uppercase tracking-widest mb-3">Tracks</p>
              <h2 className="text-4xl font-bold text-white leading-tight">
                Pick something hard.<br />
                <span className="text-zinc-500">Then build it.</span>
              </h2>
            </div>
            <Link
              to="/tracks"
              className="hidden md:inline-flex items-center gap-2 text-zinc-400 hover:text-white text-sm transition-colors border border-zinc-800 hover:border-zinc-600 px-4 py-2 rounded-lg"
            >
              All tracks →
            </Link>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {FEATURED_TRACKS.map((track) => (
              <Link
                key={track.id}
                to={`/coursedetails/${track.id}`}
                className={`group relative bg-gradient-to-br ${track.color} border ${track.border} rounded-2xl p-6 hover:border-opacity-60 transition-all hover:scale-[1.02] block`}
              >
                <div className="flex items-center justify-between mb-4">
                  <span className={`text-xs font-medium px-2.5 py-1 rounded-full border ${track.badge}`}>
                    {track.tag}
                  </span>
                  {track.available ? (
                    <span className="text-xs text-green-400 bg-green-900/30 border border-green-700/40 px-2 py-0.5 rounded-full">
                      Available
                    </span>
                  ) : (
                    <span className="text-xs text-zinc-500 bg-zinc-800 border border-zinc-700 px-2 py-0.5 rounded-full">
                      Soon
                    </span>
                  )}
                </div>
                <h3 className={`text-xl font-bold text-white mb-3 group-hover:${track.accent} transition-colors`}>
                  {track.title}
                </h3>
                <p className="text-zinc-400 text-sm leading-relaxed">{track.desc}</p>
                <div className={`mt-5 text-sm font-medium ${track.accent} flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity`}>
                  View track →
                </div>
              </Link>
            ))}
          </div>

          <div className="mt-6 md:hidden text-center">
            <Link to="/tracks" className="text-zinc-400 text-sm border border-zinc-800 px-4 py-2 rounded-lg inline-block">
              View all 7 tracks →
            </Link>
          </div>
        </div>
      </section>

      {/* Methodology */}
      <section className="py-24 px-6 bg-zinc-900/50 border-t border-zinc-800/50">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <p className="text-indigo-400 text-sm font-semibold uppercase tracking-widest mb-3">The Method</p>
            <h2 className="text-4xl font-bold text-white mb-4">
              Why 0.1% DEV is different
            </h2>
            <p className="text-zinc-400 max-w-xl mx-auto">
              Most platforms teach frameworks. We teach the knowledge underneath frameworks — the kind that doesn't go stale.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {METHODOLOGY.map((item) => (
              <div key={item.title} className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 hover:border-zinc-700 transition-colors">
                <div className="text-3xl mb-4">{item.icon}</div>
                <h3 className="text-white font-semibold mb-2">{item.title}</h3>
                <p className="text-zinc-500 text-sm leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Testimonials */}
      <section className="py-24 px-6 bg-zinc-950 border-t border-zinc-800/50">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-14">
            <p className="text-indigo-400 text-sm font-semibold uppercase tracking-widest mb-3">From the community</p>
            <h2 className="text-4xl font-bold text-white">What developers are saying</h2>
          </div>

          <div className="columns-1 sm:columns-2 lg:columns-3 gap-5 space-y-5">
            {TESTIMONIALS.map((t) => (
              <div
                key={t.img}
                className="break-inside-avoid rounded-2xl overflow-hidden border border-zinc-800 hover:border-zinc-700 transition-colors"
              >
                <img src={t.img} alt={t.alt} className="w-full h-auto block" />
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* AI Assistant CTA */}
      <section className="py-20 px-6 bg-zinc-950 border-t border-zinc-800/50">
        <div className="max-w-3xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 bg-indigo-600/10 border border-indigo-500/20 rounded-full px-4 py-1.5 mb-6">
            <span className="text-indigo-400 text-sm">✦</span>
            <span className="text-indigo-300 text-sm font-medium">AI Course Assistant</span>
          </div>
          <h2 className="text-4xl font-bold text-white mb-4">
            Questions while you learn?
          </h2>
          <p className="text-zinc-400 mb-8 text-lg leading-relaxed">
            Our RAG-powered assistant searches the course transcripts and gives you grounded, cited answers — not hallucinations. Click a source to jump straight to that moment in the lecture.
          </p>
          <Link
            to="/ask"
            className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-8 py-3.5 rounded-xl font-semibold transition-all hover:scale-[1.02] shadow-lg shadow-indigo-900/40"
          >
            <span>✦</span> Try the AI Assistant
          </Link>
        </div>
      </section>

      {/* AI Engineering section */}
      <section className="py-24 px-6 bg-zinc-950 border-t border-zinc-800/50 relative overflow-hidden">
        {/* Background glow */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-indigo-600/5 rounded-full blur-[120px] pointer-events-none" />

        <div className="max-w-7xl mx-auto relative z-10">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 items-center">
            {/* Left — headline */}
            <div>
              <div className="inline-flex items-center gap-2 bg-indigo-600/10 border border-indigo-500/20 rounded-full px-3 py-1.5 mb-6">
                <span className="text-indigo-400 text-xs font-bold uppercase tracking-widest">AI Era</span>
              </div>
              <h2 className="text-4xl md:text-5xl font-bold text-white mb-6 leading-tight">
                AI writes the code.
                <br />
                <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-purple-400">
                  You need to own it.
                </span>
              </h2>
              <p className="text-zinc-400 text-lg leading-relaxed mb-6">
                When everyone has Copilot and GPT-4, the differentiator isn't who can write a for-loop. It's who can look at AI-generated code and{" "}
                <span className="text-zinc-200 font-medium">understand why it works, when it breaks, and how to fix it.</span>
              </p>
              <p className="text-zinc-500 leading-relaxed">
                That requires knowing what's underneath. The engine, the runtime, the protocol, the data structure. The engineers who will define the AI era aren't prompt engineers — they're the ones who understand what the prompts are generating.
              </p>
            </div>

            {/* Right — cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {[
                {
                  icon: "🧠",
                  title: "AI generates, you validate",
                  desc: "GPT-4 will write you a WebSocket server. If you don't know how framing works, you can't tell if it's correct.",
                  accent: "border-indigo-500/20 bg-indigo-600/5",
                },
                {
                  icon: "⚡",
                  title: "Debugging at depth",
                  desc: "When AI code has a hidden class deoptimization or a memory leak, only someone who understands V8 can diagnose it.",
                  accent: "border-yellow-500/20 bg-yellow-600/5",
                },
                {
                  icon: "🔧",
                  title: "Architecture decisions",
                  desc: "AI can't choose your state management strategy, your real-time scaling approach, or your module design. You still own that.",
                  accent: "border-purple-500/20 bg-purple-600/5",
                },
                {
                  icon: "🎯",
                  title: "Prompt like an expert",
                  desc: "The better your mental model, the better your prompts. Knowing how a compiler works makes you 10× more effective with AI tools.",
                  accent: "border-green-500/20 bg-green-600/5",
                },
              ].map((card) => (
                <div
                  key={card.title}
                  className={`border ${card.accent} rounded-2xl p-5 hover:brightness-110 transition-all`}
                >
                  <div className="text-2xl mb-3">{card.icon}</div>
                  <h3 className="text-white font-semibold text-sm mb-2">{card.title}</h3>
                  <p className="text-zinc-500 text-xs leading-relaxed">{card.desc}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Quote */}
          <div className="mt-16 border-t border-zinc-800 pt-12 text-center">
            <blockquote className="text-xl md:text-2xl text-zinc-300 font-light italic max-w-3xl mx-auto leading-relaxed">
              "The engineers who thrive in the AI age aren't the ones who use it most —
              they're the ones who understand what it's producing."
            </blockquote>
            <p className="text-zinc-600 text-sm mt-4">— The 0.1% DEV philosophy</p>
          </div>
        </div>
      </section>

      {/* Comparison section */}
      <section className="py-24 px-6 bg-zinc-900 border-t border-zinc-800">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-14">
            <p className="text-indigo-400 text-sm font-semibold uppercase tracking-widest mb-3">Why 0.1% DEV</p>
            <h2 className="text-4xl font-bold text-white">Not all learning is equal</h2>
          </div>

          <div className="grid grid-cols-3 gap-0 rounded-2xl overflow-hidden border border-zinc-700">
            {/* Header row */}
            <div className="bg-zinc-800/60 px-6 py-4 border-b border-zinc-700 flex items-center">
              <span className="text-zinc-500 text-sm font-medium">What you get</span>
            </div>
            <div className="bg-zinc-800/60 px-6 py-4 border-b border-l border-zinc-700 flex items-center justify-center gap-3">
              <span className="text-2xl">▶</span>
              <div>
                <p className="text-zinc-300 text-sm font-semibold">YouTube / Blogs</p>
                <p className="text-zinc-600 text-xs">Free content</p>
              </div>
            </div>
            <div className="bg-indigo-950/60 px-6 py-4 border-b border-l border-indigo-800/50 flex items-center justify-center gap-3">
              <span className="text-zinc-300 font-bold text-sm">0.1%</span>
              <div>
                <p className="text-white text-sm font-semibold">0.1% DEV</p>
                <p className="text-indigo-400 text-xs">First principles</p>
              </div>
            </div>

            {/* Rows */}
            {[
              {
                label: "Depth of content",
                youtube: { text: "Surface level", bad: true },
                us: { text: "Engine-level internals", good: true },
              },
              {
                label: "What you build",
                youtube: { text: "Todo apps & clones", bad: true },
                us: { text: "Compilers, engines, libraries", good: true },
              },
              {
                label: "Source code reading",
                youtube: { text: "Rarely, if ever", bad: true },
                us: { text: "V8, Axios, Pinia, Express", good: true },
              },
              {
                label: "First principles",
                youtube: { text: "Skipped for speed", bad: true },
                us: { text: "Always. No hand-waving.", good: true },
              },
              {
                label: "What you ship",
                youtube: { text: "Nothing real", bad: true },
                us: { text: "NPM packages & benchmarked projects", good: true },
              },
              {
                label: "AI course assistant",
                youtube: { text: "❌", bad: true },
                us: { text: "✓ RAG-powered, source-cited", good: true },
              },
              {
                label: "Shelf life of knowledge",
                youtube: { text: "Expires with frameworks", bad: true },
                us: { text: "Timeless — primitives don't change", good: true },
              },
            ].map((row, i) => (
              <React.Fragment key={row.label}>
                <div className={`px-6 py-4 flex items-center border-t border-zinc-700/60 ${i % 2 === 0 ? "bg-zinc-900/40" : "bg-zinc-900/20"}`}>
                  <span className="text-zinc-400 text-sm">{row.label}</span>
                </div>
                <div className={`px-6 py-4 flex items-center border-t border-l border-zinc-700/60 ${i % 2 === 0 ? "bg-zinc-900/40" : "bg-zinc-900/20"}`}>
                  <span className="text-zinc-500 text-sm">{row.youtube.text}</span>
                </div>
                <div className={`px-6 py-4 flex items-center border-t border-l border-indigo-800/30 ${i % 2 === 0 ? "bg-indigo-950/30" : "bg-indigo-950/20"}`}>
                  <span className="text-zinc-200 text-sm">{row.us.text}</span>
                </div>
              </React.Fragment>
            ))}
          </div>
        </div>
      </section>
    </>
  );
}
