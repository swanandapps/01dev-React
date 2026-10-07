import type { ReactNode } from "react";

/** Inline `code` and **bold** inside a line of answer text. */
function inline(text: string, key: string): ReactNode[] {
  return text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).map((part, i) => {
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2)
      return <code key={`${key}-${i}`} className="font-mono text-[0.88em] bg-zinc-800 text-violet-200 rounded px-1.5 py-0.5">{part.slice(1, -1)}</code>;
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4)
      return <strong key={`${key}-${i}`} className="font-semibold text-zinc-50">{part.slice(2, -2)}</strong>;
    return part;
  });
}

/** The tutor's answer: prose with real code blocks (```…```), inline code and bold. */
export function AnswerText({ text, streaming }: { text: string; streaming?: boolean }) {
  const parts = text.split(/```[a-zA-Z]*\n?/);
  return (
    <div className="flex flex-col gap-3 text-[15px] leading-relaxed text-zinc-200">
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          <pre key={i} className="bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-3 overflow-x-auto">
            <code className="font-mono text-[13px] leading-relaxed text-zinc-200">{part.replace(/\n$/, "")}</code>
          </pre>
        ) : part.trim() ? (
          <p key={i} className="whitespace-pre-wrap">
            {inline(part.trim(), String(i))}
            {streaming && i === parts.length - 1 && (
              <span className="inline-block w-1.5 h-4 ml-0.5 align-text-bottom bg-violet-400 animate-pulse" />
            )}
          </p>
        ) : null,
      )}
    </div>
  );
}
