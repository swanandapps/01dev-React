import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Loader2, LineChart, Play, Target, Zap } from "lucide-react";
import Header from "../components/Home/Header";
import { FeatureGlimpse } from "../components/common/FeatureGlimpse";
import { comingUp } from "../components/lab/topicBits";
import { getJourney, getLabTopics, lastLecture } from "../lib/learnApi";
import type { LabTopicsResponse } from "../lib/learnApi";
import { useUserSessionStore } from "../store/userSession";
import type { Journey, ConceptStat } from "../types/learn";

const humanize = (concept: string) => {
  const s = concept.replace(/[-_]+/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
};

// Sequential, one hue (teal), light -> dark on the dark surface: more sessions, brighter.
const HEAT = ["bg-zinc-800/70", "bg-teal-900", "bg-teal-700", "bg-teal-500", "bg-teal-300"];

function Heatmap({ data }: { data: { date: string; count: number }[] }) {
  if (!data.length) return <p className="text-xs text-zinc-500">No practice yet.</p>;
  const lead = new Date(data[0].date).getDay(); // empty cells before the first day
  return (
    <div>
      <div className="grid grid-rows-7 grid-flow-col gap-1 w-max">
        {Array.from({ length: lead }).map((_, i) => <div key={`pad-${i}`} className="w-3 h-3" />)}
        {data.map((d) => (
          <div key={d.date} title={`${d.date}: ${d.count} session${d.count === 1 ? "" : "s"}`}
               className={`w-3 h-3 rounded-sm ${HEAT[Math.min(d.count, 4)]}`} />
        ))}
      </div>
      <div className="flex items-center gap-1.5 mt-3 text-[11px] text-zinc-500">
        <span>Less</span>
        {HEAT.map((c) => <span key={c} className={`w-3 h-3 rounded-sm ${c}`} />)}
        <span>More</span>
      </div>
    </div>
  );
}

function ConceptBars({ title, tint, bar, items }: { title: string; tint: string; bar: string; items: ConceptStat[] }) {
  return (
    <section className="bg-zinc-900 border border-zinc-800 rounded-2xl px-5 py-4 flex flex-col gap-3">
      <h2 className={`text-xs font-extrabold tracking-widest ${tint}`}>{title}</h2>
      {items.length === 0 ? (
        <p className="text-xs text-zinc-500">Take a few quizzes to see this.</p>
      ) : items.slice(0, 4).map((c) => {
        const pct = Math.round(c.accuracy * 100);
        return (
          <div key={c.concept} className="flex flex-col gap-1">
            <div className="flex items-center justify-between text-[13.5px]">
              <span className="text-zinc-200">{humanize(c.concept)}</span>
              <span className="text-zinc-300">{pct}%</span>
            </div>
            <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
              <div className={`h-full rounded-full ${bar}`} style={{ width: `${Math.max(pct, 3)}%` }} />
            </div>
          </div>
        );
      })}
    </section>
  );
}

function Stat({ label, value, sub }: { label: string; value: React.ReactNode; sub: string }) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-2xl px-5 py-4 flex flex-col gap-1">
      <span className="text-[13px] text-zinc-400">{label}</span>
      <span className="text-3xl font-extrabold text-zinc-50">{value}</span>
      <span className="text-xs text-zinc-500">{sub}</span>
    </div>
  );
}

export default function MyLearningPage() {
  const [journey, setJourney] = useState<Journey | null>(null);
  const [topics, setTopics] = useState<LabTopicsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const currentuser = useUserSessionStore((s) => s.currentuser);
  const isUserLoggedIn = useUserSessionStore((s) => s.isUserLoggedIn);
  const userId = (currentuser?.uid as string) || "anonymous";

  useEffect(() => {
    if (!isUserLoggedIn) return;
    getJourney(userId).then(setJourney).catch((e) => setError((e as Error).message));
    getLabTopics().then(setTopics).catch(() => setTopics(null));
  }, [userId, isUserLoggedIn]);

  const m = journey?.metrics;
  const started = (m?.quizzes ?? 0) > 0;

  if (!isUserLoggedIn) {
    return (
      <div className="bg-zinc-950 text-[#F0F0F0] min-h-screen">
        <Header />
        <div className="pt-16">
          <FeatureGlimpse
            icon={LineChart}
            title="Your learning"
            tagline="See what's solid, what needs work, and what to do next, across every course you take."
            bullets={["What to pick up today", "Each course's progress, lecture by lecture", "Your strengths, weak spots and practice activity"]}
            sample={
              <div className="grid grid-cols-3 gap-2 text-left">
                {[{ l: "Streak", v: "5 days" }, { l: "Right", v: "76%" }, { l: "Solid", v: "10 of 16" }].map((s) => (
                  <div key={s.l} className="bg-zinc-800/60 border border-zinc-700/50 rounded-lg px-3 py-2">
                    <p className="text-[10px] uppercase text-zinc-500">{s.l}</p>
                    <p className="text-base font-semibold text-zinc-100">{s.v}</p>
                  </div>
                ))}
              </div>
            }
          />
        </div>
      </div>
    );
  }

  // Pick up where you left off: the last lecture opened in the player, else the next one your Lab suggests.
  const last = lastLecture();
  const next = topics ? comingUp(topics) : null;
  const nextCourse = topics?.courses.find((c) => c.slug === next?.slug);
  const nextLecture = nextCourse?.topics.find((t) => t.index === next?.topic)?.lectures.find((l) => l.status !== "solid");
  const resume = last
    ? { title: last.title, sub: `${last.courseTitle} · where you stopped`, to: `/course/${last.courseId}?chapter=${last.chapter}&sub=${last.sub}`, cta: "Resume" }
    : nextLecture && nextCourse
    ? { title: nextLecture.title, sub: `${nextCourse.title} · next in your course`, to: `/course/${nextCourse.id}?chapter=${nextLecture.chapter}&sub=${nextLecture.sub}`, cta: "Start" }
    : null;

  // Today's focus: Lab's 'Start here' (weakest topic), else 'Keep it fresh'.
  const focusRef = topics?.start_here ?? topics?.keep_fresh ?? null;
  const focusCourse = topics?.courses.find((c) => c.slug === focusRef?.slug);
  const focusTopic = focusCourse?.topics.find((t) => t.index === focusRef?.topic);

  return (
    <div className="bg-zinc-950 text-[#F0F0F0] min-h-screen">
      <Header />
      <div className="pt-16">
        <div className="max-w-6xl mx-auto px-5 sm:px-8 py-8 flex flex-col gap-7">
          <div className="flex flex-col gap-2">
            <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-zinc-50">Your learning</h1>
            {journey?.ai.focus && (
              <p className="flex items-start gap-2 text-sm text-violet-200">
                <Zap className="w-4 h-4 flex-shrink-0 mt-0.5 text-violet-300" /> {journey.ai.focus}
              </p>
            )}
          </div>

          {(resume || focusTopic) && (
            <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {resume && (
                <article className="bg-violet-950/30 border border-violet-800/70 rounded-3xl p-5 flex items-center gap-4">
                  <span className="w-14 h-14 rounded-2xl bg-violet-900/70 text-violet-100 flex items-center justify-center flex-shrink-0">
                    <Play className="w-6 h-6 fill-current" />
                  </span>
                  <div className="flex-1 min-w-0 flex flex-col gap-1">
                    <span className="text-[11px] font-extrabold tracking-widest text-violet-300">PICK UP WHERE YOU LEFT OFF</span>
                    <span className="text-lg font-extrabold text-zinc-50 truncate">{resume.title}</span>
                    <span className="text-[13px] text-zinc-400 truncate">{resume.sub}</span>
                  </div>
                  <Link to={resume.to} className="bg-violet-600 hover:bg-violet-500 text-white font-extrabold text-sm rounded-xl px-4 py-2.5 flex-shrink-0">
                    {resume.cta}
                  </Link>
                </article>
              )}
              {focusTopic && focusCourse && focusRef && (
                <article className="bg-teal-950/30 border border-teal-800/70 rounded-3xl p-5 flex items-center gap-4">
                  <span className="w-14 h-14 rounded-2xl bg-teal-950 text-teal-300 flex items-center justify-center flex-shrink-0">
                    <Target className="w-6 h-6" />
                  </span>
                  <div className="flex-1 min-w-0 flex flex-col gap-1">
                    <span className="text-[11px] font-extrabold tracking-widest text-teal-300">TODAY'S FOCUS · FROM YOUR LAB</span>
                    <span className="text-lg font-extrabold text-zinc-50 truncate">{focusTopic.name}</span>
                    <span className="text-[13px] text-zinc-400 line-clamp-1">{focusRef.why}</span>
                  </div>
                  <Link to={`/lab/topic/${focusCourse.slug}/${focusTopic.index}`}
                        className="bg-teal-400 hover:bg-teal-300 text-teal-950 font-extrabold text-sm rounded-xl px-4 py-2.5 flex-shrink-0">
                    Work on this
                  </Link>
                </article>
              )}
            </section>
          )}

          {!journey && !error && (
            <div className="flex items-center gap-2 text-zinc-400 py-10 justify-center">
              <Loader2 className="w-5 h-5 animate-spin" /> <span className="text-sm">Loading your progress…</span>
            </div>
          )}
          {error && <p className="text-sm text-amber-300">Couldn't load your progress right now.</p>}

          {m && (
            <section className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              <Stat label="Practice streak" value={`${m.streak} day${m.streak === 1 ? "" : "s"}`} sub={`${m.active_days} active days in total`} />
              <Stat label="Questions right" value={`${Math.round(m.avg_score * 100)}%`} sub={`across ${m.quizzes} quiz${m.quizzes === 1 ? "" : "zes"}`} />
              <Stat label="Questions answered" value={`${m.questions_answered}`} sub={m.avg_seconds_per_question ? `about ${m.avg_seconds_per_question} s each` : "no timing yet"} />
              <Stat label="Concepts solid" value={<>{m.concepts_mastered} <span className="text-lg text-zinc-400">of {m.concepts_practiced}</span></>}
                    sub={m.concepts_weak ? `${m.concepts_weak} need work` : "none need work"} />
            </section>
          )}

          {topics && topics.courses.length > 0 && (
            <section className="flex flex-col gap-3">
              <div className="flex items-baseline justify-between gap-4">
                <h2 className="text-xl font-extrabold text-zinc-100">Your courses</h2>
                <span className="hidden sm:flex items-center gap-3 text-xs text-zinc-400">
                  <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-green-500" />solid</span>
                  <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-amber-500" />shaky</span>
                  <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-zinc-600" />not tried</span>
                </span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
                {topics.courses.map((c) => {
                  const lectures = c.topics.flatMap((t) => t.lectures);
                  const solid = lectures.filter((l) => l.status === "solid").length;
                  const shaky = lectures.filter((l) => l.status === "shaky").length;
                  const focusHere = topics.start_here?.slug === c.slug ? c.topics.find((t) => t.index === topics.start_here!.topic) : null;
                  const nextUp = lectures.find((l) => l.status !== "solid");
                  return (
                    <article key={c.slug} className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4 flex flex-col gap-2.5">
                      <span className="text-[15px] font-bold text-zinc-100">{c.title}</span>
                      <span className="h-2 rounded-full bg-zinc-800 flex gap-0.5 overflow-hidden" aria-hidden="true">
                        <span className="bg-green-500" style={{ width: `${(100 * solid) / (lectures.length || 1)}%` }} />
                        <span className="bg-amber-500" style={{ width: `${(100 * shaky) / (lectures.length || 1)}%` }} />
                      </span>
                      <span className="text-[12.5px] text-zinc-400">
                        {solid} of {lectures.length} lectures solid{shaky ? ` · ${shaky} shaky` : ""}
                      </span>
                      {focusHere ? (
                        <Link to={`/lab/topic/${c.slug}/${focusHere.index}`} className="text-[13px] font-bold text-teal-300 hover:text-teal-200">
                          Practise {focusHere.name} →
                        </Link>
                      ) : nextUp ? (
                        <Link to={`/course/${c.id}?chapter=${nextUp.chapter}&sub=${nextUp.sub}`} className="text-[13px] font-bold text-teal-300 hover:text-teal-200">
                          Continue {nextUp.title.split(" - ")[0]} →
                        </Link>
                      ) : (
                        <span className="text-[13px] font-bold text-green-400">All solid</span>
                      )}
                    </article>
                  );
                })}
              </div>
            </section>
          )}

          {journey && (
            <section className="grid grid-cols-1 lg:grid-cols-[1fr_1fr_1.15fr] gap-4">
              <ConceptBars title="STRENGTHS" tint="text-green-300" bar="bg-green-500" items={journey.strengths} />
              <ConceptBars title="NEEDS WORK" tint="text-amber-300" bar="bg-amber-500" items={journey.weaknesses} />
              <section className="bg-zinc-900 border border-zinc-800 rounded-2xl px-5 py-4 flex flex-col gap-3 overflow-x-auto">
                <h2 className="text-xs font-extrabold tracking-widest text-zinc-400">ACTIVITY · LAST 12 WEEKS</h2>
                {started ? <Heatmap data={journey.heatmap} /> : <p className="text-xs text-zinc-500">No practice yet.</p>}
              </section>
            </section>
          )}

          {journey && !started && (
            <Link to="/tracks" className="self-start text-sm font-semibold text-violet-300 hover:text-violet-200">Browse courses to start →</Link>
          )}
        </div>
      </div>
    </div>
  );
}
