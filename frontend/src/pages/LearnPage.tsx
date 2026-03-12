import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Sparkles, Loader2, Flame, Target, Clock, Brain, CheckCircle2, Zap, Lightbulb, LineChart } from "lucide-react";
import Header from "../components/Home/Header";
import { FeatureGlimpse } from "../components/common/FeatureGlimpse";
import { getJourney } from "../lib/learnApi";
import { useUserSessionStore } from "../store/userSession";
import type { Journey, ConceptStat } from "../types/learn";

function Metric({ icon: Icon, label, value }: { icon: typeof Flame; label: string; value: string }) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-3">
      <div className="flex items-center gap-1.5 text-zinc-500 mb-1">
        <Icon className="w-3.5 h-3.5" />
        <span className="text-[11px] uppercase tracking-wide">{label}</span>
      </div>
      <p className="text-xl font-semibold text-zinc-100">{value}</p>
    </div>
  );
}

function heatColor(count: number): string {
  if (count <= 0) return "bg-zinc-800/70";
  if (count === 1) return "bg-indigo-900";
  if (count === 2) return "bg-indigo-700";
  if (count === 3) return "bg-indigo-500";
  return "bg-indigo-400";
}

function Heatmap({ data }: { data: { date: string; count: number }[] }) {
  if (!data.length) return null;
  const lead = new Date(data[0].date).getDay(); // empty cells before the first day
  return (
    <div>
      <div className="grid grid-rows-7 grid-flow-col gap-1 w-max">
        {Array.from({ length: lead }).map((_, i) => (
          <div key={`pad-${i}`} className="w-3 h-3" />
        ))}
        {data.map((d) => (
          <div
            key={d.date}
            title={`${d.date}: ${d.count} session${d.count === 1 ? "" : "s"}`}
            className={`w-3 h-3 rounded-sm ${heatColor(d.count)}`}
          />
        ))}
      </div>
      <div className="flex items-center gap-1.5 mt-3 text-[11px] text-zinc-600">
        <span>Less</span>
        {[0, 1, 2, 3, 4].map((c) => (
          <span key={c} className={`w-3 h-3 rounded-sm ${heatColor(c)}`} />
        ))}
        <span>More</span>
      </div>
    </div>
  );
}

function ConceptList({ title, items, good }: { title: string; items: ConceptStat[]; good: boolean }) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl px-5 py-4">
      <h3 className={`text-xs font-semibold uppercase tracking-wide mb-3 ${good ? "text-emerald-400" : "text-amber-400"}`}>
        {title}
      </h3>
      {items.length === 0 ? (
        <p className="text-xs text-zinc-600">Not enough data yet.</p>
      ) : (
        <div className="space-y-2.5">
          {items.map((c) => {
            const pct = Math.round(c.accuracy * 100);
            return (
              <div key={c.concept}>
                <div className="flex items-center justify-between text-xs mb-1">
                  <span className="text-zinc-300">{c.concept}</span>
                  <span className={good ? "text-emerald-400" : "text-amber-400"}>{pct}%</span>
                </div>
                <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                  <div className={`h-full ${good ? "bg-emerald-500" : "bg-amber-500"}`} style={{ width: `${Math.max(pct, 3)}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function MyLearningPage() {
  const [journey, setJourney] = useState<Journey | null>(null);
  const [error, setError] = useState<string | null>(null);

  const currentuser = useUserSessionStore((s) => s.currentuser);
  const isUserLoggedIn = useUserSessionStore((s) => s.isUserLoggedIn);
  const userId = (currentuser?.uid as string) || "anonymous";

  useEffect(() => {
    if (!isUserLoggedIn) return;
    getJourney(userId)
      .then(setJourney)
      .catch((e) => setError((e as Error).message));
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
            title="Your Learning Journey"
            tagline="A personal analytics dashboard that turns your activity into insights — and surfaces patterns you wouldn't notice yourself."
            bullets={[
              "Streaks, mastery, time-spent and score metrics",
              "An activity heatmap of your practice",
              "AI-found patterns + a focus for what's next",
            ]}
            sample={
              <div className="grid grid-cols-3 gap-2 text-left">
                {[
                  { l: "Streak", v: "5" },
                  { l: "Avg score", v: "82%" },
                  { l: "Mastered", v: "7" },
                ].map((s) => (
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

  return (
    <div className="bg-zinc-950 text-[#F0F0F0] min-h-screen">
      <Header />
      <div className="pt-16">
        <div className="max-w-3xl mx-auto px-6 py-8">
          <div className="mb-8">
            <h1 className="text-xl font-semibold text-zinc-100">Your Journey</h1>
            <p className="text-sm text-zinc-500">Your learning analytics with 0.1% DEV</p>
          </div>

          {!journey && !error && (
            <div className="flex items-center gap-2 text-zinc-400 py-16 justify-center">
              <Loader2 className="w-5 h-5 animate-spin" />
              <span className="text-sm">Analyzing your journey…</span>
            </div>
          )}
          {error && <p className="text-sm text-amber-300">{error}</p>}

          {journey && m && (
            <div className="space-y-8">
              {/* AI narrative */}
              <div className="bg-gradient-to-br from-indigo-950/40 to-zinc-900 border border-indigo-500/20 rounded-2xl px-6 py-5">
                <div className="flex items-center gap-2 mb-2">
                  <Sparkles className="w-4 h-4 text-indigo-400" />
                  <span className="text-xs font-semibold text-indigo-300 uppercase tracking-wide">Your story so far</span>
                </div>
                <p className="text-sm text-zinc-200 leading-relaxed">{journey.ai.narrative}</p>
                {journey.ai.focus && (
                  <div className="mt-3 flex items-start gap-2 text-sm text-indigo-200 bg-indigo-500/10 border border-indigo-500/20 rounded-lg px-3 py-2">
                    <Zap className="w-4 h-4 flex-shrink-0 mt-0.5" />
                    <span><span className="font-medium">Focus:</span> {journey.ai.focus}</span>
                  </div>
                )}
                {!started && (
                  <Link to="/tracks" className="inline-flex items-center gap-1.5 mt-4 text-sm font-medium text-indigo-300 hover:text-indigo-200">
                    Browse courses to start →
                  </Link>
                )}
              </div>

              {/* metrics */}
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                <Metric icon={Flame} label="Day streak" value={`${m.streak}`} />
                <Metric icon={Target} label="Avg score" value={`${Math.round(m.avg_score * 100)}%`} />
                <Metric icon={Brain} label="Concepts mastered" value={`${m.concepts_mastered}`} />
                <Metric icon={Zap} label="Quizzes" value={`${m.quizzes}`} />
                <Metric icon={Clock} label="Practiced" value={`${m.practice_minutes}m`} />
                <Metric icon={CheckCircle2} label="Avg / question" value={m.avg_seconds_per_question ? `${m.avg_seconds_per_question}s` : "—"} />
              </div>

              {/* activity heatmap */}
              {started && (
                <section>
                  <h2 className="text-sm font-semibold text-zinc-100 mb-3">Activity · last 12 weeks</h2>
                  <div className="bg-zinc-900 border border-zinc-800 rounded-xl px-5 py-4 overflow-x-auto">
                    <Heatmap data={journey.heatmap} />
                  </div>
                </section>
              )}

              {/* strengths / weaknesses */}
              {started && (
                <div className="grid sm:grid-cols-2 gap-4">
                  <ConceptList title="Your strengths" items={journey.strengths} good />
                  <ConceptList title="Focus areas" items={journey.weaknesses} good={false} />
                </div>
              )}

              {/* AI insights */}
              {journey.ai.insights.length > 0 && (
                <section>
                  <div className="flex items-center gap-2 mb-3">
                    <Lightbulb className="w-4 h-4 text-amber-400" />
                    <h2 className="text-sm font-semibold text-zinc-100">Patterns we noticed</h2>
                  </div>
                  <div className="space-y-2">
                    {journey.ai.insights.map((ins, i) => (
                      <div key={i} className="flex items-start gap-2.5 bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-3">
                        <span className="text-amber-500 mt-0.5">✦</span>
                        <p className="text-sm text-zinc-300 leading-relaxed">{ins}</p>
                      </div>
                    ))}
                  </div>
                </section>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
