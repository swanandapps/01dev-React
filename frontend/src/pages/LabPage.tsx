import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ChevronRight, Plus, X } from "lucide-react";
import Header from "../components/Home/Header";
import { LabStudio } from "../components/lab/LabStudio";
import { STATUS_CHIP, STATUS_LABEL, TopicBar, comingUp } from "../components/lab/topicBits";
import { useUserSessionStore } from "../store/userSession";
import { getCourses, getEnrollment, getLabTopics } from "../lib/learnApi";
import type { LabTopicsResponse } from "../lib/learnApi";
import type { Course } from "../types/learn";

const topicUrl = (slug: string, index: number) => `/lab/topic/${slug}/${index}`;

export default function LabPage() {
  const navigate = useNavigate();
  const { currentuser, isUserLoggedIn } = useUserSessionStore();
  const studentId = (currentuser?.uid as string) || "";
  const [data, setData] = useState<LabTopicsResponse | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [courses, setCourses] = useState<Course[]>([]);
  const [ownOpen, setOwnOpen] = useState(false);

  useEffect(() => {
    if (!isUserLoggedIn || !studentId) { setLoaded(true); return; }
    // Signed in (or sign-in just restored): wait for topics before choosing which Lab to show.
    setLoaded(false);
    getLabTopics().then(setData).catch(() => setData(null)).finally(() => setLoaded(true));
    Promise.all([getCourses(), getEnrollment(studentId)])
      .then(([all, owned]) => {
        const titles = new Set(owned.map((c) => c.title));
        setCourses(all.filter((c) => titles.has(c.title) && c.lecture_count > 0));
      })
      .catch(() => setCourses([]));
  }, [isUserLoggedIn, studentId]);

  const find = (ref: { slug: string; topic: number } | null) => {
    if (!ref || !data) return null;
    const course = data.courses.find((c) => c.slug === ref.slug);
    const topic = course?.topics.find((t) => t.index === ref.topic);
    return course && topic ? { course, topic } : null;
  };
  const start = data?.start_here ? find(data.start_here) : null;
  const next = data ? find(comingUp(data)) : null;
  const fresh = data?.keep_fresh ? find(data.keep_fresh) : null;
  // The big card: your weakest topic, or — before any quiz — what's coming up in your course.
  const hero = start ?? next;
  const heroWhy = start ? data!.start_here!.why : "Next in your course. Get it solid before you move on.";
  const side = [
    ...(start && next && (next.topic.index !== start.topic.index || next.course.slug !== start.course.slug)
      ? [{ ...next, tag: "COMING UP IN YOUR COURSE", tint: "text-violet-300", why: "Get a head start before you reach it.", cta: "Work on this" }] : []),
    ...(fresh ? [{ ...fresh, tag: "KEEP IT FRESH", tint: "text-sky-300", why: data!.keep_fresh!.why, cta: "Review" }] : []),
  ];
  const hasTopics = !!data && data.courses.length > 0;

  return (
    <div className="bg-zinc-950 min-h-screen">
      <Header />
      <div className="max-w-6xl mx-auto px-5 sm:px-8 pt-24 pb-16 flex flex-col gap-10">
        <section className="flex flex-col gap-2">
          <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight text-zinc-50">Your Lab</h1>
          <p className="text-base sm:text-lg text-zinc-400 max-w-3xl min-h-[3.5rem]">
            {!loaded ? "" : hasTopics
              ? "The topics worth your time right now, picked from how you're doing in your courses. Pick one and work on it."
              : "Practise what you're learning: quizzes, flashcards and study plans from your lectures, notes or a PDF."}
          </p>
        </section>

        {!loaded && <div className="h-56 rounded-3xl bg-zinc-900 animate-pulse" />}

        {hasTopics && hero && (
          <section className={`grid grid-cols-1 gap-4 ${side.length ? "lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]" : ""}`}>
            <article className="bg-teal-950/30 border border-teal-500/70 rounded-3xl p-6 sm:p-7 flex flex-col gap-5">
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs font-extrabold tracking-widest text-teal-300">START HERE</span>
                <span className="text-xs text-zinc-400">{hero.course.title}</span>
              </div>
              <div className="flex flex-col gap-2">
                <h2 className="text-3xl font-extrabold tracking-tight text-zinc-50">{hero.topic.name}</h2>
                <p className="text-[15px] text-zinc-300 leading-relaxed">{heroWhy}</p>
              </div>
              <ul className="flex flex-wrap gap-2">
                {hero.topic.lectures.map((l) => (
                  <li key={l.title} className={`text-[13px] border rounded-full px-3 py-1 ${STATUS_CHIP[l.status]}`}>
                    {l.title.split(" - ")[0]} · {STATUS_LABEL[l.status]}
                  </li>
                ))}
              </ul>
              <div className="flex flex-wrap items-center gap-4">
                <button onClick={() => navigate(topicUrl(hero.course.slug, hero.topic.index))}
                        className="bg-teal-400 hover:bg-teal-300 text-teal-950 font-extrabold rounded-xl px-6 py-3.5">
                  Work on this
                </button>
                <span className="text-sm text-zinc-400">
                  {hero.topic.solid} of {hero.topic.lectures.length} lectures solid
                </span>
              </div>
            </article>

            {side.length > 0 && (
              <div className="flex flex-col gap-4">
                {side.map((s) => (
                  <article key={s.tag} className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5 flex flex-col gap-3">
                    <div className="flex items-center justify-between gap-3">
                      <span className={`text-[11px] font-extrabold tracking-widest ${s.tint}`}>{s.tag}</span>
                      <span className="text-xs text-zinc-500">{s.course.title}</span>
                    </div>
                    <h3 className="text-xl font-extrabold text-zinc-50">{s.topic.name}</h3>
                    <p className="text-[13.5px] text-zinc-400 leading-relaxed">{s.why}</p>
                    <div className="flex items-center gap-3">
                      <TopicBar topic={s.topic} className="flex-1" />
                      <span className="text-xs text-zinc-400">{s.topic.solid} of {s.topic.lectures.length} solid</span>
                    </div>
                    <Link to={topicUrl(s.course.slug, s.topic.index)} className="self-start text-sm font-bold text-teal-300 hover:text-teal-200">
                      {s.cta} →
                    </Link>
                  </article>
                ))}
              </div>
            )}
          </section>
        )}

        {hasTopics && data!.courses.map((c) => (
          <section key={c.slug} className="flex flex-col gap-3">
            <div className="flex items-baseline justify-between gap-4">
              <h2 className="text-xl font-bold text-zinc-100">All topics · {c.title}</h2>
              <span className="text-xs text-zinc-500 hidden sm:flex items-center gap-3">
                <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-green-500" />solid</span>
                <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-amber-500" />shaky</span>
                <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-zinc-600" />not tried</span>
              </span>
            </div>
            <div className="border border-zinc-800 rounded-2xl overflow-hidden divide-y divide-zinc-800/80">
              {c.topics.map((t) => (
                <Link key={t.index} to={topicUrl(c.slug, t.index)}
                      className="flex items-center gap-4 px-4 sm:px-5 py-3.5 bg-zinc-950 hover:bg-zinc-900 transition-colors">
                  <span className="w-7 h-7 rounded-full bg-zinc-800 text-zinc-300 text-xs font-bold flex items-center justify-center flex-shrink-0">{t.index + 1}</span>
                  <span className="flex-1 min-w-0 text-[15px] font-semibold text-zinc-100 truncate">{t.name}</span>
                  <TopicBar topic={t} className="w-28 sm:w-40 flex-shrink-0" />
                  <span className="text-xs text-zinc-500 w-24 text-right flex-shrink-0">{t.solid}/{t.lectures.length} solid</span>
                  <ChevronRight className="w-4 h-4 text-zinc-600 flex-shrink-0" />
                </Link>
              ))}
            </div>
          </section>
        ))}

        {loaded && <section className="flex flex-col gap-5">
          {hasTopics && !ownOpen ? (
            <div className="flex flex-wrap items-center gap-4 bg-zinc-900 border border-dashed border-zinc-700 rounded-2xl px-5 py-4">
              <div className="flex-1 min-w-[240px]">
                <p className="text-[15px] font-bold text-zinc-100">Working on something outside your courses?</p>
                <p className="text-[13.5px] text-zinc-400">Practise from a topic name, your notes or a PDF.</p>
              </div>
              <button onClick={() => setOwnOpen(true)}
                      className="flex items-center gap-2 border border-zinc-600 hover:border-zinc-400 text-zinc-100 font-bold text-sm rounded-xl px-4 py-2.5">
                <Plus className="w-4 h-4" /> Add your own topic
              </button>
            </div>
          ) : (
            <div className="flex flex-col gap-5">
              {hasTopics && (
                <div className="flex items-center justify-between">
                  <h2 className="text-xl font-bold text-zinc-100">Your own topic</h2>
                  <button onClick={() => setOwnOpen(false)} aria-label="Close" className="text-zinc-500 hover:text-zinc-200"><X className="w-5 h-5" /></button>
                </div>
              )}
              <LabStudio studentId={studentId} onClose={() => (hasTopics ? setOwnOpen(false) : navigate(-1))}
                         courses={courses} chrome={false} />
            </div>
          )}
        </section>}
      </div>
    </div>
  );
}
