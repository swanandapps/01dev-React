import { useEffect, useState } from "react";
import { useParams, Navigate } from "react-router-dom";
import { Sparkles } from "lucide-react";
import Header from "../components/Home/Header";
import TracksMain from "../components/Tracks/Main";
import Footer from "../components/Home/Footer";
import { CourseCompanion } from "../components/learn/CourseCompanion";
import { getCourses } from "../lib/learnApi";
import { useUserSessionStore } from "../store/userSession";
import tracks from "../data/tracks";
import type { Course } from "../types/learn";

export default function CourseDetailsPage() {
  const { courseid } = useParams<{ courseid: string }>();
  const track = tracks.find((t) => t.id === Number(courseid));

  const currentuser = useUserSessionStore((s) => s.currentuser);
  const userId = (currentuser?.uid as string) || "anonymous";

  // Match this catalog course to a backend course (by title) that has transcripts.
  const [aiCourse, setAiCourse] = useState<Course | null>(null);
  useEffect(() => {
    if (!track) return;
    getCourses()
      .then((courses) => setAiCourse(courses.find((c) => c.title === track.title) ?? null))
      .catch(() => setAiCourse(null));
  }, [track]);

  if (!track) return <Navigate to="/tracks" replace />;

  return (
    <div className="bg-zinc-950 text-[#F0F0F0]">
      <Header />
      <TracksMain track={track} />

      {aiCourse && (
        <div className="max-w-6xl mx-auto px-6 -mt-2 mb-12">
          <div className="bg-gradient-to-br from-indigo-950/40 to-zinc-900 border border-indigo-500/20 rounded-2xl px-6 py-5">
            <div className="flex items-center gap-2 mb-1.5">
              <Sparkles className="w-4 h-4 text-indigo-400" />
              <h3 className="text-base font-semibold text-zinc-100">Learn this course with AI</h3>
            </div>
            <p className="text-sm text-zinc-500 mb-4">
              An AI study companion for the whole course — a structured guide, a practice quiz, and
              adaptive practice that adjusts to how you're doing.
            </p>
            <CourseCompanion course={aiCourse} userId={userId} />
          </div>
        </div>
      )}

      <Footer />
    </div>
  );
}
