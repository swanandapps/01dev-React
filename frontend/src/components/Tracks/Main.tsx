import { useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";
import { Check, ChevronDown, GraduationCap, ListChecks, TrendingUp } from "lucide-react";
import { useUserSessionStore } from "../../store/userSession";
import { getCourses, enrollCourse } from "../../lib/learnApi";
import { CourseCompanion } from "../learn/CourseCompanion";
import type { Course } from "../../types/learn";
import type { Track } from "../../data/tracks";

declare global {
  interface Window {
    Razorpay: new (options: Record<string, unknown>) => { open: () => void };
  }
}

interface Props {
  track: Track;
}

export default function TracksMain({ track }: Props) {
  const navigate = useNavigate();
  const { isUserLoggedIn, isCourseBought, currency, currentuser, currentuserhistory, setCurrentUserHistory } =
    useUserSessionStore();
  const [paying, setPaying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openChapter, setOpenChapter] = useState(0);

  // Match this catalog course to a backend course (by title) that has transcripts.
  const userId = (currentuser?.uid as string) || "anonymous";
  const [aiCourse, setAiCourse] = useState<Course | null>(null);
  useEffect(() => {
    getCourses()
      .then((courses) => setAiCourse(courses.find((c) => c.title === track.title) ?? null))
      .catch(() => setAiCourse(null));
  }, [track.title]);

  const bought = isCourseBought(track.id);
  const price =
    currency === "₹"
      ? `₹${(parseInt(track.priceINR) / 100).toLocaleString("en-IN")}`
      : `$${track.priceELSE}`;

  const handleBuy = async () => {
    if (!isUserLoggedIn) {
      navigate("/signin");
      return;
    }
    setError(null);
    setPaying(true);
    try {
      const API_BASE = import.meta.env.VITE_RAG_API_URL || "http://localhost:8080";
      const res = await fetch(`${API_BASE}/api/paymentRZ`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          amount: currency === "₹" ? track.priceINR : String(parseInt(track.priceELSE) * 100),
          currency: currency === "₹" ? "INR" : "USD",
          courseId: track.id,
        }),
      });
      if (!res.ok) throw new Error(`Payment server error ${res.status}`);
      const data = await res.json();

      const user = currentuser as { uid?: string; displayName?: string; email?: string };

      const options = {
        key: import.meta.env.VITE_RAZORPAY_KEY_ID,
        amount: data.amount,
        currency: data.currency,
        name: "0.1% DEV",
        description: track.title,
        order_id: data.id,
        handler: async () => {
          // Save purchase — enrollment is Postgres (backend), not Firestore.
          // Firebase stays scoped to auth + storage.
          if (user.uid) {
            try {
              await enrollCourse({ student_id: user.uid, course_id: track.id, course_title: track.title });
              // Update local store so UI reflects purchase immediately
              const updated = {
                ...currentuserhistory,
                PrevCourses: [
                  ...((currentuserhistory as { PrevCourses?: { id: number }[] }).PrevCourses || []),
                  { id: track.id },
                ],
              };
              setCurrentUserHistory(updated, "purchase", true);
            } catch (e) {
              console.error("Enrollment save failed", e);
            }
          }
          navigate(`/course/${track.id}`);
        },
        modal: {
          ondismiss: () => setPaying(false),
        },
        prefill: {
          name: user.displayName || "",
          email: user.email || "",
        },
        theme: { color: "#18181b" },
      };

      const rzp = new window.Razorpay(options);
      rzp.open();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Payment failed. Please try again.");
      setPaying(false);
    }
  };

  const lectureCount = track.courseContent.reduce((n, c) => n + c.subchapters.length, 0);
  const tools = [
    { icon: GraduationCap, tint: "bg-violet-500/15 text-violet-300", title: "A tutor in every lecture",
      text: "Ask about what's on screen, or say “take me to” any part of the course." },
    { icon: ListChecks, tint: "bg-teal-500/15 text-teal-300", title: "Check yourself as you go",
      text: "Quick quizzes and flashcards made from each lecture." },
    { icon: TrendingUp, tint: "bg-sky-500/15 text-sky-300", title: "See your weak spots",
      text: "Progress by concept, with what to revise next." },
  ];

  return (
    <div className="min-h-screen bg-zinc-950 pt-24 pb-20 px-5 sm:px-8">
      <div className="max-w-6xl mx-auto grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_380px] gap-10 lg:gap-12">
        <main className="flex flex-col gap-12 min-w-0">
          <section className="flex flex-col gap-4">
            <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight text-white">{track.title}</h1>
            <p className="text-zinc-400 text-lg leading-relaxed">{track.description}</p>
            <p className="text-sm text-zinc-300">
              {track.courseContent.length} chapters <span className="text-zinc-600 mx-1.5">·</span> {lectureCount} lectures
            </p>
          </section>

          {track.modules.length > 0 && (
            <section className="flex flex-col gap-4">
              <h2 className="text-2xl font-bold text-white">What you'll build</h2>
              <ol className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
                {track.modules.map((mod, i) => (
                  <li key={i} className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4 flex flex-col gap-2">
                    <span className="font-mono text-xs text-violet-300">{String(i + 1).padStart(2, "0")}</span>
                    <h3 className="text-[15px] font-semibold text-zinc-100">{mod.title}</h3>
                    <p className="text-[13px] text-zinc-400 leading-relaxed">{mod.description}</p>
                  </li>
                ))}
              </ol>
            </section>
          )}

          {track.learnings.length > 0 && (
            <section className="flex flex-col gap-4">
              <h2 className="text-2xl font-bold text-white">What you'll learn</h2>
              <ul className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-3">
                {track.learnings.map((l, i) => (
                  <li key={i} className="flex items-start gap-2.5 text-[15px] text-zinc-300">
                    <Check className="w-4 h-4 mt-1 flex-shrink-0 text-violet-400" />
                    <span>{l}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section className="flex flex-col gap-4">
            <div className="flex items-baseline justify-between gap-4">
              <h2 className="text-2xl font-bold text-white">Curriculum</h2>
              <span className="text-sm text-zinc-400">{track.courseContent.length} chapters · {lectureCount} lectures</span>
            </div>
            <div className="border border-zinc-800 rounded-2xl overflow-hidden divide-y divide-zinc-800/80">
              {track.courseContent.map((chapter, ci) => {
                const open = openChapter === ci;
                return (
                  <div key={ci} className={open ? "bg-zinc-900" : "bg-zinc-950"}>
                    <button
                      onClick={() => setOpenChapter(open ? -1 : ci)}
                      aria-expanded={open}
                      className="w-full flex items-center gap-3.5 px-4 sm:px-5 py-3.5 text-left hover:bg-zinc-900 transition-colors"
                    >
                      <span className={`w-7 h-7 rounded-full flex-shrink-0 flex items-center justify-center text-xs font-bold ${
                        open ? "bg-violet-600 text-white" : "bg-zinc-800 text-zinc-300"}`}>{ci + 1}</span>
                      <span className="flex-1 min-w-0 text-[15px] font-semibold text-zinc-100">
                        {chapter.name.replace(/^Chapter\s+\d+\s*-\s*/, "")}
                      </span>
                      <span className="text-[13px] text-zinc-500 flex-shrink-0">
                        {chapter.subchapters.length} {chapter.subchapters.length === 1 ? "lecture" : "lectures"}
                      </span>
                      <ChevronDown className={`w-4 h-4 text-zinc-500 flex-shrink-0 transition-transform ${open ? "rotate-180" : ""}`} />
                    </button>
                    {open && (
                      <ul className="pl-[60px] pr-5 pb-4 flex flex-col gap-2.5">
                        {chapter.subchapters.map((sc, j) => {
                          const m = sc.name.match(/^(\d+\.\d+)\s*-\s*(.*)$/);
                          return (
                            <li key={j} className="flex items-baseline gap-3 text-sm text-zinc-300">
                              <span className="font-mono text-xs text-zinc-500 w-8 flex-shrink-0">{m ? m[1] : ""}</span>
                              <span>{m ? m[2] : sc.name}</span>
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </div>
                );
              })}
            </div>
          </section>

          {track.testimonials && track.testimonials.length > 0 && (
            <section className="flex flex-col gap-4">
              <h2 className="text-2xl font-bold text-white">What students say</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {track.testimonials.map((t, i) => (
                  <figure key={i} className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5 flex flex-col gap-3">
                    <blockquote className="text-[15px] leading-relaxed text-zinc-200">“{t.quote}”</blockquote>
                    <figcaption className="text-[13px] text-zinc-400">{t.name}{t.source ? ` · ${t.source}` : ""}</figcaption>
                  </figure>
                ))}
              </div>
            </section>
          )}
        </main>

        <aside className="lg:row-start-1 lg:col-start-2">
          <div className="lg:sticky lg:top-24 bg-zinc-900 border border-zinc-800 rounded-2xl overflow-hidden">
            {track.trailer && (
              <video autoPlay muted loop playsInline className="w-full aspect-video object-cover" src={track.trailer} />
            )}

            <div className="p-6 flex flex-col gap-4">
              <div className="flex items-baseline gap-2.5">
                <span className="text-3xl font-extrabold text-white">{price}</span>
                <span className="text-[13px] text-zinc-400">one-time · lifetime access</span>
              </div>

              {error && (
                <p className="text-red-300 text-xs bg-red-900/20 border border-red-800/40 rounded-lg px-3 py-2">{error}</p>
              )}

              {bought ? (
                <button
                  onClick={() => navigate(`/course/${track.id}`)}
                  className={`w-full py-3.5 rounded-xl font-bold text-white ${track.theme2} transition-colors`}
                >
                  Continue learning →
                </button>
              ) : (
                <button
                  onClick={handleBuy}
                  disabled={paying}
                  className={`w-full py-3.5 rounded-xl font-bold text-white ${track.theme2} transition-all disabled:opacity-50 disabled:cursor-not-allowed`}
                >
                  {paying ? "Opening checkout…" : "Buy this course"}
                </button>
              )}
              <p className="text-xs text-zinc-500 -mt-1">All future updates included.</p>

              <div className="border-t border-zinc-800 pt-4 flex flex-col gap-3.5">
                <span className="text-[11px] font-bold tracking-widest text-zinc-400">
                  {bought ? "YOUR LEARNING TOOLS" : "LEARNING TOOLS INCLUDED"}
                </span>
                {bought && aiCourse ? (
                  <CourseCompanion course={aiCourse} userId={userId} size="sm" />
                ) : (
                  tools.map((t) => (
                    <div key={t.title} className="flex gap-3 items-start">
                      <span className={`w-8 h-8 rounded-lg flex-shrink-0 flex items-center justify-center ${t.tint}`}>
                        <t.icon className="w-4 h-4" />
                      </span>
                      <span className="flex flex-col gap-0.5">
                        <span className="text-sm font-semibold text-zinc-100">{t.title}</span>
                        <span className="text-[12.5px] text-zinc-400 leading-snug">{t.text}</span>
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
