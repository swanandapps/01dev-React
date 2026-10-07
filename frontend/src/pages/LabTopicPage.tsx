import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Play, Layers, ListChecks } from "lucide-react";
import Header from "../components/Home/Header";
import { LabStudio } from "../components/lab/LabStudio";
import { QuickQuiz } from "../components/learn/QuickQuiz";
import { STATUS_CHIP, STATUS_DOT, STATUS_LABEL, TopicBar, needsWork } from "../components/lab/topicBits";
import { useUserSessionStore } from "../store/userSession";
import { getLabTopics, startTopicQuiz } from "../lib/learnApi";
import type { LabTopic, LabTopicsResponse, LectureStatus } from "../lib/learnApi";

type Moved = { title: string; from: LectureStatus; to: LectureStatus };

export default function LabTopicPage() {
  const { slug = "", index = "0" } = useParams();
  const chapter = Number(index);
  const { currentuser, isUserLoggedIn } = useUserSessionStore();
  const studentId = (currentuser?.uid as string) || "";
  const [data, setData] = useState<LabTopicsResponse | null>(null);
  const [error, setError] = useState(false);
  const [quiz, setQuiz] = useState<{ kind: "topic" } | { kind: "lecture"; title: string } | null>(null);
  const [flashcards, setFlashcards] = useState<string | null>(null);
  const [before, setBefore] = useState<LabTopic | null>(null);
  const [moved, setMoved] = useState<Moved[] | null>(null);

  const load = useCallback(() => getLabTopics().then(setData).catch(() => setError(true)), []);
  useEffect(() => { if (isUserLoggedIn) void load(); }, [isUserLoggedIn, load]);

  const course = data?.courses.find((c) => c.slug === slug);
  const topic = course?.topics.find((t) => t.index === chapter);

  // After a session: compare each lecture's status before and after, and show what moved.
  useEffect(() => {
    if (!before || !topic || topic === before) return;
    const changes = topic.lectures
      .map((l, i) => ({ title: l.title, from: before.lectures[i]?.status, to: l.status }))
      .filter((m): m is Moved => !!m.from && m.from !== m.to);
    setMoved(changes);
    setBefore(null);
  }, [topic, before]);

  if (!isUserLoggedIn) {
    return (
      <div className="bg-zinc-950 min-h-screen"><Header />
        <p className="pt-32 text-center text-zinc-400">Sign in to work on your topics.</p>
      </div>
    );
  }
  if (error || (data && !topic)) {
    return (
      <div className="bg-zinc-950 min-h-screen"><Header />
        <div className="pt-32 text-center flex flex-col items-center gap-3">
          <p className="text-zinc-400">This topic isn't available.</p>
          <Link to="/lab" className="text-teal-300 font-semibold">Back to your Lab</Link>
        </div>
      </div>
    );
  }
  if (!topic || !course) {
    return <div className="bg-zinc-950 min-h-screen"><Header /><div className="max-w-6xl mx-auto px-8 pt-28"><div className="h-64 rounded-3xl bg-zinc-900 animate-pulse" /></div></div>;
  }

  const focus = needsWork(topic);
  const total = topic.lectures.length;
  const player = (l: { chapter: number; sub: number }) => `/course/${course.id}?chapter=${l.chapter}&sub=${l.sub}`;

  return (
    <div className="bg-zinc-950 min-h-screen">
      <Header />
      <div className="max-w-6xl mx-auto px-5 sm:px-8 pt-24 pb-16 flex flex-col gap-8">
        <section className="flex flex-col gap-3">
          <Link to="/lab" className="self-start flex items-center gap-1.5 text-sm text-zinc-400 hover:text-zinc-200">
            <ArrowLeft className="w-4 h-4" /> Your Lab
          </Link>
          <div className="flex flex-wrap items-end justify-between gap-5">
            <div className="flex flex-col gap-1.5">
              <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-zinc-50">{topic.name}</h1>
              <p className="text-sm text-zinc-400">{course.title} · Chapter {topic.index + 1}</p>
            </div>
            <div className="flex flex-col items-start sm:items-end gap-2 min-w-[220px]">
              <span className="text-sm text-zinc-300">{topic.solid} of {total} lectures solid</span>
              <TopicBar topic={topic} className="w-full sm:w-60" />
            </div>
          </div>
        </section>

        {moved && (
          <section className="bg-zinc-900 border border-zinc-700 rounded-2xl p-5 flex flex-col gap-3">
            <h2 className="text-base font-extrabold text-zinc-50">
              {moved.length ? "What moved in this session" : "Session saved. Nothing changed status yet. Keep going."}
            </h2>
            {moved.map((m) => (
              <div key={m.title} className="flex flex-wrap items-center gap-2.5 text-sm">
                <span className="flex-1 min-w-[200px] text-zinc-200">{m.title}</span>
                <span className={`text-xs border rounded-full px-2.5 py-0.5 ${STATUS_CHIP[m.from]}`}>{STATUS_LABEL[m.from]}</span>
                <span className="text-zinc-500">→</span>
                <span className={`text-xs border rounded-full px-2.5 py-0.5 ${STATUS_CHIP[m.to]}`}>{STATUS_LABEL[m.to]}</span>
              </div>
            ))}
          </section>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_300px] gap-8">
          <div className="flex flex-col gap-8 min-w-0">
            <section className="bg-teal-950/30 border border-teal-500/70 rounded-3xl p-6 flex flex-col gap-4">
              <div className="flex flex-wrap items-baseline justify-between gap-3">
                <h2 className="text-xl font-extrabold text-zinc-50">Practise this topic</h2>
                <span className="text-sm text-teal-200/80">{Math.min(focus.length, 3) * 2} questions, focused on what needs work</span>
              </div>
              <ol className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {focus.map((l) => (
                  <li key={l.title} className="bg-zinc-950/60 border border-teal-900 rounded-2xl p-4 flex flex-col gap-1.5">
                    <span className={`self-start text-[11px] border rounded-full px-2 py-0.5 ${STATUS_CHIP[l.status]}`}>{STATUS_LABEL[l.status]}</span>
                    <span className="text-sm font-bold text-zinc-100 leading-snug">{l.title}</span>
                    <span className="text-xs text-zinc-400">2 questions</span>
                  </li>
                ))}
              </ol>
              <button onClick={() => { setBefore(topic); setMoved(null); setQuiz({ kind: "topic" }); }}
                      className="self-start bg-teal-400 hover:bg-teal-300 text-teal-950 font-extrabold rounded-xl px-6 py-3.5">
                Start
              </button>
            </section>

            <section className="flex flex-col gap-3">
              <h2 className="text-lg font-extrabold text-zinc-100">Lectures in this topic</h2>
              <ul className="border border-zinc-800 rounded-2xl overflow-hidden divide-y divide-zinc-800/80">
                {topic.lectures.map((l) => (
                  <li key={l.title} className="flex flex-wrap items-center gap-3 sm:gap-4 px-4 sm:px-5 py-3.5 bg-zinc-950">
                    <span className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${STATUS_DOT[l.status]}`} aria-label={STATUS_LABEL[l.status]} />
                    <span className="flex-1 min-w-[180px] text-[15px] font-semibold text-zinc-100">{l.title}</span>
                    <span className="text-xs text-zinc-400 w-24">{l.total ? `${l.right} of ${l.total} right` : "not tried"}</span>
                    <span className="flex items-center gap-1.5">
                      <Link to={player(l)} className="flex items-center gap-1.5 text-xs font-semibold text-zinc-200 border border-zinc-700 hover:border-zinc-500 rounded-lg px-2.5 py-1.5">
                        <Play className="w-3.5 h-3.5" /> Watch
                      </Link>
                      <button onClick={() => { setBefore(topic); setMoved(null); setQuiz({ kind: "lecture", title: l.title }); }}
                              className="flex items-center gap-1.5 text-xs font-semibold text-teal-200 border border-teal-900 hover:border-teal-600 rounded-lg px-2.5 py-1.5">
                        <ListChecks className="w-3.5 h-3.5" /> Quiz me
                      </button>
                      <button onClick={() => setFlashcards(l.title)}
                              className="flex items-center gap-1.5 text-xs font-semibold text-zinc-200 border border-zinc-700 hover:border-zinc-500 rounded-lg px-2.5 py-1.5">
                        <Layers className="w-3.5 h-3.5" /> Flashcards
                      </button>
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          </div>

          <aside className="flex flex-col gap-3">
            <h2 className="text-xs font-extrabold tracking-widest text-zinc-400">HOW THIS WORKS</h2>
            <p className="text-sm text-zinc-400 leading-relaxed">
              Each lecture is <span className="text-green-300">solid</span> when you get at least 80% of its questions
              right, <span className="text-amber-300">shaky</span> below that, and <span className="text-zinc-300">not tried</span> until
              you answer some. Every quiz you take, here or in the player, updates it.
            </p>
          </aside>
        </div>
      </div>

      {quiz && (
        <QuickQuiz
          courseSlug={course.slug}
          lecture={quiz.kind === "lecture" ? quiz.title : `${topic.name} · topic practice`}
          title={quiz.kind === "topic" ? `Practise · ${topic.name}` : "Check yourself"}
          start={quiz.kind === "topic" ? () => startTopicQuiz(course.slug, topic.index) : undefined}
          onSubmitted={() => void load()}
          onClose={() => setQuiz(null)}
        />
      )}

      {flashcards && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" onClick={() => setFlashcards(null)}>
          <div className="bg-zinc-900 border border-zinc-700/60 rounded-2xl w-full max-w-xl max-h-[90vh] overflow-y-auto p-6"
               onClick={(e) => e.stopPropagation()}>
            <LabStudio studentId={studentId} courseId={course.slug} onClose={() => setFlashcards(null)}
                       initialLectureTitle={flashcards} initialOutputs={["flashcards"]} autoStart />
          </div>
        </div>
      )}
    </div>
  );
}
