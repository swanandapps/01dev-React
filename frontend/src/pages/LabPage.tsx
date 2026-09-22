import { useNavigate } from "react-router-dom";
import { Sparkles, FlaskConical, ShieldCheck } from "lucide-react";
import Header from "../components/Home/Header";
import { LabStudio } from "../components/lab/LabStudio";
import { useUserSessionStore } from "../store/userSession";

export default function LabPage() {
  const navigate = useNavigate();
  const { currentuser } = useUserSessionStore();
  const studentId = (currentuser?.uid as string) || "";

  return (
    <div className="bg-zinc-950 min-h-screen">
      <Header />
      <div className="max-w-2xl mx-auto px-4 pt-24 pb-16">
        <div className="mb-8">
          <div className="flex items-center gap-2 mb-4">
            <div className="w-10 h-10 rounded-xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center">
              <FlaskConical className="w-5 h-5 text-indigo-400" />
            </div>
            <div className="flex items-center gap-1.5 text-xs font-semibold text-indigo-400 uppercase tracking-wide">
              <Sparkles className="w-3.5 h-3.5" /> AI Feature
            </div>
            <span className="ml-auto flex items-center gap-1.5 text-xs text-emerald-400 bg-emerald-950/40 px-2.5 py-1 rounded-full border border-emerald-800/50">
              <ShieldCheck className="w-3.5 h-3.5" /> Grounded &amp; audited
            </span>
          </div>
          <h1 className="text-2xl font-bold text-zinc-100 mb-2">Lab</h1>
          <p className="text-sm text-zinc-500 leading-relaxed max-w-lg">
            Bring your own material — type a topic, paste notes, upload a PDF, or pick a
            lecture — then choose what to make from it: a quiz, flashcards, a quick
            revision summary, a study plan, or all of them.
          </p>
        </div>

        <LabStudio studentId={studentId} onClose={() => navigate(-1)} />
      </div>
    </div>
  );
}
