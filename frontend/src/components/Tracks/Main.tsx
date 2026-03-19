import { useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";
import { Sparkles } from "lucide-react";
import { useUserSessionStore } from "../../store/userSession";
import { db } from "../../lib/firebase";
import { doc, updateDoc, arrayUnion } from "firebase/firestore";
import { getCourses } from "../../lib/learnApi";
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
          // Save purchase to Firestore
          if (user.uid) {
            try {
              await updateDoc(doc(db, "users", user.uid), {
                PrevCourses: arrayUnion({ id: track.id, title: track.title, purchasedAt: new Date().toISOString() }),
              });
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
              console.error("Firestore update failed", e);
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

  return (
    <div className="min-h-screen bg-zinc-950 pt-24 pb-16 px-6">
      <div className="max-w-5xl mx-auto">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-12">
          {/* Left column */}
          <div className="lg:col-span-2">
            <h1 className="text-4xl font-bold text-white mb-4">{track.title}</h1>
            <p className="text-zinc-400 text-lg mb-10 leading-relaxed">{track.description}</p>

            {track.learnings.length > 0 && (
              <div className="mb-10">
                <h2 className="text-xl font-semibold text-white mb-5">What you'll learn</h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {track.learnings.map((l, i) => (
                    <div key={i} className="flex items-start gap-2.5 text-zinc-400 text-sm">
                      <span className={`mt-0.5 font-bold ${track.theme}`}>✓</span>
                      <span>{l}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {aiCourse && (
              <div className="mb-10 bg-gradient-to-br from-indigo-950/40 to-zinc-900 border border-indigo-500/20 rounded-2xl px-6 py-5">
                <div className="flex items-center gap-2 mb-1.5">
                  <Sparkles className="w-4 h-4 text-indigo-400" />
                  <h2 className="text-base font-semibold text-zinc-100">Learn this course with AI</h2>
                </div>
                <p className="text-sm text-zinc-500 mb-4 leading-relaxed">
                  An AI study companion for the whole course — a structured guide, a practice quiz,
                  and adaptive practice that adjusts to how you're doing.
                </p>
                <CourseCompanion course={aiCourse} userId={userId} />
              </div>
            )}

            {track.modules.length > 0 && (
              <div className="mb-10">
                <h2 className="text-xl font-semibold text-white mb-5">Modules</h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {track.modules.map((mod, i) => (
                    <div key={i} className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
                      <h3 className="text-zinc-200 font-medium text-sm mb-1">{mod.title}</h3>
                      <p className="text-zinc-500 text-xs leading-relaxed">{mod.description}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="mb-10">
              <h2 className="text-xl font-semibold text-white mb-5">Course content</h2>
              <div className="space-y-2">
                {track.courseContent.map((chapter, i) => (
                  <details key={i} className="bg-zinc-900 rounded-xl border border-zinc-800">
                    <summary className="px-4 py-3 cursor-pointer text-zinc-300 font-medium text-sm flex items-center justify-between hover:text-white select-none">
                      {chapter.name}
                      <span className="text-zinc-600 text-xs">{chapter.subchapters.length} lectures</span>
                    </summary>
                    <div className="px-4 pb-3 space-y-0.5">
                      {chapter.subchapters.map((sc, j) => (
                        <div key={j} className="text-zinc-500 text-sm py-1.5 pl-3 border-l border-zinc-700 flex items-center gap-2">
                          <span className="text-zinc-700 text-xs">▶</span>
                          {sc.name}
                        </div>
                      ))}
                    </div>
                  </details>
                ))}
              </div>
            </div>
          </div>

          {/* Sticky sidebar */}
          <div className="lg:col-span-1">
            <div className="sticky top-24 bg-zinc-900 border border-zinc-800 rounded-2xl overflow-hidden">
              {track.trailer && (
                <video
                  autoPlay
                  muted
                  loop
                  playsInline
                  className="w-full aspect-video object-cover"
                  src={track.trailer}
                />
              )}

              <div className="p-6">
                <div className="text-3xl font-bold text-white mb-1">{price}</div>
                <p className="text-zinc-500 text-sm mb-1">One-time · Lifetime access</p>
                <p className="text-zinc-600 text-xs mb-6">All future updates included</p>

                {error && (
                  <p className="text-red-400 text-xs mb-4 bg-red-900/20 border border-red-800/40 rounded-lg px-3 py-2">
                    {error}
                  </p>
                )}

                {bought ? (
                  <button
                    onClick={() => navigate(`/course/${track.id}`)}
                    className={`w-full py-3 rounded-xl font-semibold text-white ${track.theme2} transition-colors`}
                  >
                    Continue Track →
                  </button>
                ) : track.launched ? (
                  <button
                    onClick={handleBuy}
                    disabled={paying}
                    className={`w-full py-3.5 rounded-xl font-semibold text-white ${track.theme2} transition-all disabled:opacity-50 disabled:cursor-not-allowed`}
                  >
                    {paying ? "Opening checkout…" : "Buy Track"}
                  </button>
                ) : (
                  <button
                    onClick={handleBuy}
                    disabled={paying}
                    className={`w-full py-3.5 rounded-xl font-semibold text-white ${track.theme2} transition-all disabled:opacity-50 disabled:cursor-not-allowed`}
                  >
                    {paying ? "Opening checkout…" : "Buy Now →"}
                  </button>
                )}

                <div className="mt-6 space-y-2 text-xs text-zinc-600">
                  <div className="flex items-center gap-2">
                    <span>✓</span><span>Lifetime access to all content</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span>✓</span><span>All future updates included</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span>✓</span><span>AI course assistant access</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
