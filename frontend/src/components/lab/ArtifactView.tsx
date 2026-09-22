import { Layers, FileText, ListOrdered } from "lucide-react";
import { FlashcardDeck } from "./FlashcardDeck";
import type { Flashcard, LabArtifacts, StudyPlanStep } from "../../lib/labApi";

const META = {
  flashcards: { icon: Layers, title: "Flashcards" },
  summary: { icon: FileText, title: "Quick revision" },
  study_plan: { icon: ListOrdered, title: "Study plan" },
} as const;

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

            {key === "flashcards" && (
              <FlashcardDeck cards={(artifacts.flashcards ?? []) as Flashcard[]} />
            )}

            {key === "summary" && (
              <p className="text-sm text-zinc-300 leading-relaxed bg-zinc-800/40 border border-zinc-700/50 rounded-xl px-4 py-4">
                {artifacts.summary as string}
              </p>
            )}

            {key === "study_plan" && (
              <ol className="flex flex-col gap-2">
                {((artifacts.study_plan ?? []) as StudyPlanStep[]).map((s) => (
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
            )}
          </div>
        );
      })}
    </div>
  );
}
