import { Layers, FileText, ListOrdered } from "lucide-react";
import { FlashcardDeck } from "./FlashcardDeck";
import type { Flashcard, LabArtifacts, StudyPlanStep } from "../../lib/labApi";

const META = {
  flashcards: { icon: Layers, title: "Flashcards" },
  summary: { icon: FileText, title: "Quick revision" },
  study_plan: { icon: ListOrdered, title: "Study plan" },
} as const;

// The generators drop malformed items, so an empty list/string is a real,
// reachable outcome — not just a loading gap. Silence is the worst option
// here: show a short, honest message instead of an icon over blank space.
function EmptyNote({ title }: { title: string }) {
  return (
    <p className="text-sm text-zinc-500 bg-zinc-800/30 border border-zinc-700/40 rounded-xl px-4 py-4">
      Nothing usable came back for {title.toLowerCase()} — try again or add more material.
    </p>
  );
}

export function ArtifactView({ artifacts }: { artifacts: LabArtifacts }) {
  const present = (Object.keys(META) as (keyof typeof META)[]).filter(
    (k) => artifacts[k] !== undefined,
  );
  if (!present.length) return null;

  return (
    <div className="flex flex-col gap-5">
      {present.map((key) => {
        const { icon: Icon, title } = META[key];
        return (
          <div key={key}>
            <div className="flex items-center gap-2 mb-2.5">
              <Icon className="w-4 h-4 text-indigo-400" />
              <p className="text-xs font-semibold text-indigo-400 uppercase tracking-wide">
                {title}
              </p>
            </div>

            {key === "flashcards" && (() => {
              const cards = (artifacts.flashcards ?? []) as Flashcard[];
              return cards.length
                ? <FlashcardDeck cards={cards} />
                : <EmptyNote title={title} />;
            })()}

            {key === "summary" && (() => {
              const summary = ((artifacts.summary as string | undefined) ?? "").trim();
              return summary
                ? (
                  <p className="text-sm text-zinc-300 leading-relaxed bg-zinc-800/40 border border-zinc-700/50 rounded-xl px-4 py-4">
                    {summary}
                  </p>
                )
                : <EmptyNote title={title} />;
            })()}

            {key === "study_plan" && (() => {
              const steps = (artifacts.study_plan ?? []) as StudyPlanStep[];
              return steps.length
                ? (
                  <ol className="flex flex-col gap-2">
                    {steps.map((s) => (
                      <li key={s.step}
                          className="bg-zinc-800/60 border border-zinc-700/60 rounded-xl px-4 py-3 flex gap-3">
                        <span className="w-6 h-6 rounded-lg bg-indigo-600/20 text-indigo-400 text-xs font-bold flex items-center justify-center flex-shrink-0">
                          {s.step}
                        </span>
                        <div>
                          <p className="text-sm font-semibold text-zinc-100">{s.title}</p>
                          {s.detail && <p className="text-xs text-zinc-500 mt-0.5">{s.detail}</p>}
                        </div>
                      </li>
                    ))}
                  </ol>
                )
                : <EmptyNote title={title} />;
            })()}
          </div>
        );
      })}
    </div>
  );
}
