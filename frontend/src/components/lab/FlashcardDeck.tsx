import { useState } from "react";
import { ChevronLeft, ChevronRight, RotateCcw } from "lucide-react";
import type { Flashcard } from "../../lib/labApi";

export function FlashcardDeck({ cards }: { cards: Flashcard[] }) {
  const [i, setI] = useState(0);
  const [flipped, setFlipped] = useState(false);
  if (!cards.length) return null;
  const card = cards[i];

  const go = (delta: number) => {
    setI((n) => (n + delta + cards.length) % cards.length);
    setFlipped(false);
  };

  return (
    <div className="flex flex-col gap-3">
      <button
        onClick={() => setFlipped((f) => !f)}
        className="w-full min-h-[160px] bg-zinc-800/60 border border-zinc-700/60 hover:border-indigo-500/40 rounded-xl p-6 text-left transition-colors flex flex-col justify-center"
      >
        <p className="text-[10px] font-bold uppercase tracking-wide text-indigo-400 mb-2">
          {flipped ? "Back" : "Front"}
        </p>
        <p className="text-base text-zinc-100 leading-relaxed">
          {flipped ? card.back : card.front}
        </p>
        <p className="text-xs text-zinc-600 mt-3">Click to flip</p>
      </button>

      <div className="flex items-center gap-2">
        <button onClick={() => go(-1)} aria-label="Previous card"
          className="p-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300">
          <ChevronLeft className="w-4 h-4" />
        </button>
        <span className="text-xs text-zinc-500 flex-1 text-center">
          {i + 1} / {cards.length}
        </span>
        <button onClick={() => setFlipped(false)} aria-label="Reset flip"
          className="p-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300">
          <RotateCcw className="w-4 h-4" />
        </button>
        <button onClick={() => go(1)} aria-label="Next card"
          className="p-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300">
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
