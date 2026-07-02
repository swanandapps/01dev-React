import { useNavigate } from "react-router-dom";
import { Sparkles, NotebookPen } from "lucide-react";
import Header from "../components/Home/Header";
import { NotesQuizModal } from "../components/learn/NotesQuizModal";

export default function NotesQuizPage() {
  const navigate = useNavigate();
  return (
    <div className="bg-zinc-950 min-h-screen">
      <Header />
      <div className="max-w-2xl mx-auto px-4 pt-24 pb-16">
        {/* hero */}
        <div className="mb-8">
          <div className="flex items-center gap-2 mb-4">
            <div className="w-10 h-10 rounded-xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center">
              <NotebookPen className="w-5 h-5 text-indigo-400" />
            </div>
            <div className="flex items-center gap-1.5 text-xs font-semibold text-indigo-400 uppercase tracking-wide">
              <Sparkles className="w-3.5 h-3.5" /> AI Feature
            </div>
          </div>
          <h1 className="text-2xl font-bold text-zinc-100 mb-2">Notes → Quiz</h1>
          <p className="text-sm text-zinc-500 leading-relaxed max-w-lg">
            Paste your notes, type a topic, or upload a PDF — the AI drafts a lesson plan,
            you approve it, then work through an adaptive quiz with hints and a Socratic tutor.
          </p>
        </div>

        {/* quiz flow */}
        <NotesQuizModal variant="page" onClose={() => navigate(-1)} />
      </div>
    </div>
  );
}
