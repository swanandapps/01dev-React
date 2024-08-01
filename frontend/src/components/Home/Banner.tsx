import React from "react";
import { Link } from "react-router-dom";
import { useEffect, useState, useMemo } from "react";

const SNIPPETS = [
  {
    label: "Build a Compiler",
    tag: "Track 01",
    code: `function tokenize(src) {
  const tokens = [];
  let i = 0;
  while (i < src.length) {
    if (/\\d/.test(src[i])) {
      let n = '';
      while (/\\d/.test(src[i])) n += src[i++];
      tokens.push({ type: 'NUM', value: n });
    } else {
      tokens.push({ type: src[i] });
      i++;
    }
  }
  return tokens;
}`,
  },
  {
    label: "Build a Custom Library",
    tag: "Track 02",
    code: `function Library() {}

Library.prototype.use = function(plugin) {
  plugin(this);
  return this; // chainable
};

const lib = new Library();
lib.use(ajax).use(router).use(store);
// → ship to NPM`,
  },
  {
    label: "JS Engine Internals",
    tag: "Track 07",
    code: `class Vector {
  constructor(x, y) {
    this.x = x; // shape: { x }
    this.y = y; // shape: { x, y }
  }
}
// same shape = shared hidden class
// monomorphic inline cache ✓
// 100x faster property access
const v = new Vector(1, 2);`,
  },
];

const FLOAT_CONCEPTS = [
  "tokenizer","parser","AST","prototype","hidden class",
  "bytecode","V8","TurboFan","JIT","closure","scope",
  "garbage collection","WebSocket","TCP","event loop",
  "Proxy","Reflect","npm publish","Ignition","inline cache",
  "heap","call stack","hoisting","coercion","WeakRef",
];

type Token = { text: string; cls: string };

function tokenizeLine(line: string): Token[] {
  const tokens: Token[] = [];
  let rest = line;
  while (rest.length > 0) {
    let m: RegExpMatchArray | null;

    if ((m = rest.match(/^(['"`])((?:[^'"`\\]|\\.)*)\1/))) {
      tokens.push({ text: m[0], cls: "text-emerald-400" });
      rest = rest.slice(m[0].length);
      continue;
    }
    if ((m = rest.match(/^(function|const|let|var|while|return|if|else|class|new|this|for|of|import|export|from|async|await)\b/))) {
      tokens.push({ text: m[0], cls: "text-violet-400" });
      rest = rest.slice(m[0].length);
      continue;
    }
    if ((m = rest.match(/^\b\d[\d_]*\b/))) {
      tokens.push({ text: m[0], cls: "text-amber-400" });
      rest = rest.slice(m[0].length);
      continue;
    }
    if ((m = rest.match(/^[a-zA-Z_$][a-zA-Z0-9_$]*/))) {
      tokens.push({ text: m[0], cls: "text-zinc-200" });
      rest = rest.slice(m[0].length);
      continue;
    }
    if ((m = rest.match(/^ +/))) {
      tokens.push({ text: m[0], cls: "" });
      rest = rest.slice(m[0].length);
      continue;
    }
    tokens.push({ text: rest[0], cls: "text-zinc-500" });
    rest = rest.slice(1);
  }
  return tokens;
}

function buildTokens(code: string): Token[] {
  const all: Token[] = [];
  const lines = code.split("\n");
  for (let i = 0; i < lines.length; i++) {
    if (i > 0) all.push({ text: "\n", cls: "" });
    const line = lines[i];
    const commentIdx = line.indexOf("//");
    if (commentIdx !== -1) {
      const before = line.slice(0, commentIdx);
      const comment = line.slice(commentIdx);
      all.push(...tokenizeLine(before));
      all.push({ text: comment, cls: "text-zinc-500" });
    } else {
      all.push(...tokenizeLine(line));
    }
  }
  return all;
}

function RevealedCode({ tokens, charCount }: { tokens: Token[]; charCount: number }) {
  let remaining = charCount;
  const els: React.ReactNode[] = [];
  for (let i = 0; i < tokens.length && remaining > 0; i++) {
    const tok = tokens[i];
    if (tok.text === "\n") {
      els.push(<br key={i} />);
      remaining--;
    } else {
      const shown = tok.text.slice(0, remaining);
      remaining -= tok.text.length;
      if (shown) {
        els.push(
          tok.cls
            ? <span key={i} className={tok.cls}>{shown}</span>
            : <span key={i}>{shown}</span>
        );
      }
    }
  }
  return <>{els}</>;
}

const CHAR_SPEED = 28;
const PAUSE_AFTER = 2200;
const FADE_DURATION = 350;

export default function Banner() {
  const [snippetIdx, setSnippetIdx] = useState(0);
  const [charCount, setCharCount] = useState(0);
  const [phase, setPhase] = useState<"typing" | "pausing" | "fading">("typing");
  const [opacity, setOpacity] = useState(1);

  const handleTabClick = (idx: number) => {
    if (idx === snippetIdx && phase === "typing") return;
    setOpacity(0);
    setPhase("fading");
    setTimeout(() => {
      setSnippetIdx(idx);
      setCharCount(0);
      setOpacity(1);
      setPhase("typing");
    }, FADE_DURATION);
  };

  const snippet = SNIPPETS[snippetIdx];
  const tokens = useMemo(() => buildTokens(snippet.code), [snippetIdx]);
  const totalChars = snippet.code.length;

  // Typewriter logic
  useEffect(() => {
    if (phase === "typing") {
      if (charCount >= totalChars) {
        setPhase("pausing");
        return;
      }
      const t = setTimeout(() => setCharCount((c) => c + 1), CHAR_SPEED);
      return () => clearTimeout(t);
    }
    if (phase === "pausing") {
      const t = setTimeout(() => setPhase("fading"), PAUSE_AFTER);
      return () => clearTimeout(t);
    }
    if (phase === "fading") {
      setOpacity(0);
      const t = setTimeout(() => {
        setSnippetIdx((s) => (s + 1) % SNIPPETS.length);
        setCharCount(0);
        setOpacity(1);
        setPhase("typing");
      }, FADE_DURATION);
      return () => clearTimeout(t);
    }
  }, [phase, charCount, totalChars]);

  // Pre-compute float positions deterministically
  const floaters = useMemo(() =>
    FLOAT_CONCEPTS.map((word, i) => ({
      word,
      left: ((i * 19 + 7) % 93) + 2,
      delay: (i * 2.1) % 28,
      duration: 18 + (i * 1.9) % 16,
      size: i % 3 === 0 ? "text-sm" : "text-xs",
    })),
  []);

  return (
    <section className="relative min-h-screen flex items-center overflow-hidden bg-zinc-950">
      {/* Inject float-up keyframe */}
      <style>{`
        @keyframes float-up {
          0%   { transform: translateY(0); opacity: 0; }
          8%   { opacity: 0.25; }
          92%  { opacity: 0.25; }
          100% { transform: translateY(-110vh); opacity: 0; }
        }
      `}</style>

      {/* Floating concept words — very subtle */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none select-none">
        {floaters.map(({ word, left, delay, duration, size }) => (
          <span
            key={word}
            className={`absolute bottom-0 font-mono ${size} text-zinc-500`}
            style={{
              left: `${left}%`,
              animation: `float-up ${duration}s linear ${delay}s infinite`,
            }}
          >
            {word}
          </span>
        ))}
      </div>

      {/* Grid pattern */}
      <div
        className="absolute inset-0 opacity-[0.025]"
        style={{
          backgroundImage: `linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)`,
          backgroundSize: "64px 64px",
        }}
      />

      {/* Glows */}
      <div className="absolute top-1/3 left-1/4 w-[600px] h-[400px] bg-indigo-600/10 rounded-full blur-[130px] pointer-events-none" />
      <div className="absolute bottom-10 right-1/4 w-[350px] h-[250px] bg-purple-600/8 rounded-full blur-[100px] pointer-events-none" />

      <div className="relative z-10 w-full max-w-7xl mx-auto px-6 pt-28 pb-16">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-16 items-center">

          {/* Left — headline */}
          <div>
            <div className="inline-flex items-center gap-2 bg-zinc-900 border border-zinc-700 rounded-full px-4 py-1.5 mb-8">
              <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
              <span className="text-zinc-300 text-sm">7 tracks · 100+ hours · First principles</span>
            </div>

            <h1 className="text-5xl sm:text-6xl lg:text-7xl font-bold text-white mb-6 leading-[1.05] tracking-tight drop-shadow-lg">
              Become{" "}
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 via-purple-400 to-pink-400">
                'THAT'
              </span>
              <br />Developer.
            </h1>

            <p className="text-zinc-300 text-lg mb-10 max-w-lg leading-relaxed">
              Most courses teach you how to use tools.{" "}
              <span className="text-white font-medium">We teach you how to build them.</span>{" "}
              Compilers, libraries, engines — from first principles.
            </p>

            <div className="flex flex-col sm:flex-row items-start gap-4 mb-14">
              <Link
                to="/tracks"
                className="bg-white text-black px-7 py-3.5 rounded-xl font-semibold hover:bg-zinc-100 transition-all hover:scale-[1.02] shadow-lg shadow-white/10"
              >
                Explore Tracks →
              </Link>
              <Link
                to="/ask"
                className="flex items-center gap-2 bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 hover:border-indigo-500/50 text-zinc-300 hover:text-white px-7 py-3.5 rounded-xl font-semibold transition-all"
              >
                <span className="text-indigo-400">✦</span> Ask AI
              </Link>
            </div>

            <div className="border-t border-zinc-800/60 pt-8 grid grid-cols-4 gap-4 max-w-sm">
              {[
                { value: "7", label: "Tracks" },
                { value: "100+", label: "Hours" },
                { value: "0%", label: "Surface theory" },
                { value: "∞", label: "Depth" },
              ].map((s) => (
                <div key={s.label} className="text-center">
                  <div className="text-xl font-bold text-white mb-0.5">{s.value}</div>
                  <div className="text-zinc-500 text-xs">{s.label}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Right — terminal */}
          <div className="hidden lg:block">
            <div
              className="bg-zinc-900 border border-zinc-800 rounded-2xl overflow-hidden shadow-2xl shadow-black/50 transition-opacity"
              style={{ opacity, transition: `opacity ${FADE_DURATION}ms ease` }}
            >
              {/* Terminal chrome */}
              <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800 bg-zinc-950/80">
                {/* Traffic lights */}
                <div className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-red-500/70" />
                  <span className="w-2.5 h-2.5 rounded-full bg-yellow-500/70" />
                  <span className="w-2.5 h-2.5 rounded-full bg-green-500/70" />
                </div>
                {/* Current label + arrows */}
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => handleTabClick((snippetIdx - 1 + SNIPPETS.length) % SNIPPETS.length)}
                    className="text-zinc-500 hover:text-white transition-colors px-1"
                  >
                    ‹
                  </button>
                  <div className="text-center min-w-[180px]">
                    <span className="text-indigo-400 text-xs font-mono mr-2">{snippet.tag}</span>
                    <span className="text-zinc-300 text-xs font-medium">{snippet.label}</span>
                  </div>
                  <button
                    onClick={() => handleTabClick((snippetIdx + 1) % SNIPPETS.length)}
                    className="text-zinc-500 hover:text-white transition-colors px-1"
                  >
                    ›
                  </button>
                </div>
                {/* Dot indicators */}
                <div className="flex items-center gap-1.5">
                  {SNIPPETS.map((_, i) => (
                    <button
                      key={i}
                      onClick={() => handleTabClick(i)}
                      className={`w-1.5 h-1.5 rounded-full transition-colors ${i === snippetIdx ? "bg-indigo-400" : "bg-zinc-700 hover:bg-zinc-500"}`}
                    />
                  ))}
                </div>
              </div>

              {/* Code area */}
              <div className="p-5 min-h-[260px]">
                <pre className="font-mono text-sm leading-relaxed">
                  <RevealedCode tokens={tokens} charCount={charCount} />
                  {phase !== "fading" && (
                    <span className="inline-block w-[2px] h-[1em] bg-indigo-400 ml-px align-middle animate-pulse" />
                  )}
                </pre>
              </div>

              {/* Footer bar */}
              <div className="px-5 py-2 border-t border-zinc-800 bg-zinc-950/40 flex items-center justify-between">
                <span className="text-zinc-600 text-xs font-mono">javascript</span>
                <span className="text-zinc-600 text-xs font-mono">
                  {phase === "typing" ? `${charCount} / ${totalChars} chars` : phase === "pausing" ? "ready" : "..."}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
