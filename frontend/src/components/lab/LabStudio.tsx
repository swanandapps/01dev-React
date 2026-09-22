// Placeholder — the real studio (output picker, upload/paste, generation UI,
// library) is built in the next task. This stub exists only so LabPage.tsx
// and the build compile in the meantime; it is expected to be replaced
// wholesale, not extended.
import { FlaskConical } from "lucide-react";

export function LabStudio({
  studentId,
  onClose,
}: {
  studentId: string;
  onClose: () => void;
}) {
  void studentId;
  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-8 text-center">
      <FlaskConical className="w-8 h-8 text-indigo-400 mx-auto mb-3" />
      <p className="text-sm text-zinc-400">The Lab studio is coming soon.</p>
      <button
        type="button"
        onClick={onClose}
        className="mt-4 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
      >
        Go back
      </button>
    </div>
  );
}
