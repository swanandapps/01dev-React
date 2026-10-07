import { useParams, Navigate, useSearchParams } from "react-router-dom";
import { useState, useRef, useEffect } from "react";
import Header from "../components/Home/Header";
import tracks from "../data/tracks";
import { useUserSessionStore } from "../store/userSession";
import { decodeVideoUrl } from "../lib/videoDecoder";
import { recordLectureView, getCourses } from "../lib/learnApi";
import { FlaskConical, ListVideo, Sparkles } from "lucide-react";
import { LabStudio } from "../components/lab/LabStudio";
import { PlayerTutor } from "../components/learn/PlayerTutor";
import { resolveJump } from "../lib/lectureMatch";
import type { TutorNavigate } from "../lib/learnApi";
import type { Course } from "../types/learn";

export default function CoursePlayerPage() {
  const { courseid } = useParams<{ courseid: string }>();
  const [searchParams] = useSearchParams();
  const { isCourseBought, currentuser, isUserLoggedIn } = useUserSessionStore();
  const userId = (currentuser?.uid as string) || "anonymous";
  // Right rail (layout B): Chapters | AI Tutor | Lab. The tutor can pop out into a floating window.
  const [railTab, setRailTab] = useState<"chapters" | "tutor" | "lab">("chapters");
  const [tutorFloating, setTutorFloating] = useState(false);

  const track = tracks.find((t) => t.id === Number(courseid));

  // Match this course to a backend course (by title) so the in-player tutor is available.
  const [aiCourse, setAiCourse] = useState<Course | null>(null);
  useEffect(() => {
    if (!track) return;
    let cancelled = false;
    const match = (courses: Course[]) => courses.find((c) => c.title === track.title) ?? null;

    // 1) Show the button instantly from a cached course list (covers revisits).
    try {
      const cached = JSON.parse(localStorage.getItem("courses_cache") || "null");
      if (cached) setAiCourse(match(cached));
    } catch { /* ignore */ }

    // 2) Refresh from the backend, retrying through cold starts so the button
    //    reliably appears even if the backend was asleep on first load.
    const load = (attempt = 0) => {
      getCourses()
        .then((courses) => {
          if (cancelled) return;
          localStorage.setItem("courses_cache", JSON.stringify(courses));
          setAiCourse(match(courses));
        })
        .catch(() => {
          if (!cancelled && attempt < 6) setTimeout(() => load(attempt + 1), 4000);
        });
    };
    load();
    return () => { cancelled = true; };
  }, [track]);

  if (!track) return <Navigate to="/tracks" replace />;

  const bought = isCourseBought(track.id);

  const initialChapter = parseInt(searchParams.get("chapter") || "0");
  const initialSub = parseInt(searchParams.get("sub") || "0");

  const [activeChapter, setActiveChapter] = useState(initialChapter);
  const [activeSub, setActiveSub] = useState(initialSub);
  const [expandedChapter, setExpandedChapter] = useState(initialChapter);

  const videoRef = useRef<HTMLVideoElement>(null);
  const seekTarget = useRef<number | null>(null);
  // Live mirrors for the tutor jump: its callback outlives the render that created it.
  const activeRef = useRef({ chapter: initialChapter, sub: initialSub });
  activeRef.current = { chapter: activeChapter, sub: activeSub };
  const pendingMeta = useRef<(() => void) | null>(null);
  const jumpToRef = useRef<(nav: TutorNavigate) => boolean>(() => false);
  const clearPendingMeta = () => {
    if (pendingMeta.current) videoRef.current?.removeEventListener("loadedmetadata", pendingMeta.current);
    pendingMeta.current = null;
  };

  const FREE_CHAPTERS = 0;
  const seekSeconds = parseInt(searchParams.get("t") || "0");

  const currentSub = track.courseContent[activeChapter]?.subchapters[activeSub];

  const getVideoSrc = (src: string): string => {
    if (!src) return "";
    if (src.startsWith("http")) return src;
    try {
      return decodeVideoUrl(src);
    } catch {
      return src;
    }
  };

  const isLocked = (chapterIndex: number): boolean => {
    if (bought) return false;
    return chapterIndex >= FREE_CHAPTERS;
  };

  const handleSelectSub = (ci: number, si: number) => {
    if (isLocked(ci)) return;
    setActiveChapter(ci);
    setActiveSub(si);
  };

  useEffect(() => {
    clearPendingMeta(); // a same-lecture seek waiting on metadata belongs to the old video
    if (videoRef.current) {
      videoRef.current.load();
      videoRef.current.play().catch(() => {});
    }
    // Track lecture opens so the course insight can detect rewatched lectures.
    if (currentSub?.name) recordLectureView(currentSub.name);
  }, [activeChapter, activeSub]);

  useEffect(() => {
    if (!seekSeconds || !videoRef.current) return;
    seekTarget.current = seekSeconds;
  }, [seekSeconds]);

  const handleCanPlay = () => {
    if (seekTarget.current && videoRef.current) {
      videoRef.current.currentTime = seekTarget.current;
      seekTarget.current = null;
    }
  };

  // The tutor's "take me to …" (spec §3.3): switch to the lecture, seek, play.
  // Returns false (no jump, no link) for an unknown or locked lecture.
  const jumpTo = (nav: TutorNavigate): boolean => {
    const pos = resolveJump(track.courseContent, nav.lecture_title, isLocked);
    if (!pos) return false;
    setExpandedChapter(pos.chapter);
    const v = videoRef.current;
    clearPendingMeta();
    const live = activeRef.current; // the lecture on screen NOW, not at send time
    if (pos.chapter === live.chapter && pos.sub === live.sub && v) {
      seekTarget.current = null; // nothing for a later canplay to yank
      if (v.readyState >= 1) v.currentTime = nav.start_time; // metadata loaded: seek now
      else {
        // Seek directly once metadata arrives (handleCanPlay ignores a 0 target).
        const apply = () => { v.currentTime = nav.start_time; pendingMeta.current = null; };
        pendingMeta.current = apply;
        v.addEventListener("loadedmetadata", apply, { once: true });
      }
      v.play().catch(() => {});
    } else {
      // The [activeChapter, activeSub] effect reloads + plays; handleCanPlay applies the seek.
      seekTarget.current = nav.start_time;
      setActiveChapter(pos.chapter);
      setActiveSub(pos.sub);
    }
    return true;
  };
  jumpToRef.current = jumpTo;

  return (
    <div className="bg-zinc-950 text-[#F0F0F0] min-h-screen">
      <Header />
      <div className="pt-16 flex flex-col lg:flex-row h-[calc(100vh-64px)]">
        <div className="flex-1 bg-black flex flex-col">
          <div className="aspect-video w-full bg-black">
            {currentSub && !isLocked(activeChapter) ? (
              <video
                ref={videoRef}
                controls
                className="w-full h-full"
                src={getVideoSrc(currentSub.src)}
                onCanPlay={handleCanPlay}
              />
            ) : isLocked(activeChapter) ? (
              <div className="w-full h-full flex items-center justify-center">
                <div className="text-center">
                  <div className="text-4xl mb-4">🔒</div>
                  <p className="text-zinc-400 mb-4">Purchase the course to unlock this chapter</p>
                  <button
                    onClick={() => window.location.href = `/coursedetails/${track.id}`}
                    className={`${track.theme2} text-white px-6 py-3 rounded-xl font-semibold`}
                  >
                    Buy Course
                  </button>
                </div>
              </div>
            ) : (
              <div className="w-full h-full flex items-center justify-center">
                <p className="text-zinc-500">Select a lecture to start</p>
              </div>
            )}
          </div>

          <div className="p-6">
            <h2 className="text-xl font-semibold text-white">
              {currentSub?.name || "Select a lecture"}
            </h2>
            <p className="text-zinc-500 text-sm mt-1">
              {track.courseContent[activeChapter]?.name}
            </p>
          </div>
        </div>

        <aside className="w-full lg:w-[400px] flex-shrink-0 bg-zinc-900 border-l border-zinc-800 flex flex-col min-h-[70vh] lg:min-h-0">
          <div role="tablist" aria-label="Course panel" className="flex items-center gap-1 px-3 py-2.5 border-b border-zinc-800 flex-shrink-0">
            {([
              ["chapters", "Chapters", ListVideo],
              ...(aiCourse ? [["tutor", "AI Tutor", Sparkles], ["lab", "Lab", FlaskConical]] as const : []),
            ] as const).map(([id, label, Icon]) => (
              <button
                key={id}
                role="tab"
                aria-selected={railTab === id}
                onClick={() => setRailTab(id)}
                className={`flex items-center gap-1.5 text-sm rounded-lg px-3 py-2 transition-colors ${
                  railTab === id
                    ? id === "lab"
                      ? "bg-teal-600/15 border border-teal-500/40 text-teal-100 font-semibold"
                      : "bg-indigo-600/15 border border-indigo-500/40 text-indigo-100 font-semibold"
                    : "border border-transparent text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800"
                }`}
              >
                <Icon className="w-4 h-4" /> {label}
              </button>
            ))}
          </div>

          <div className="flex-1 min-h-0 flex flex-col">
            {railTab === "chapters" && (
              <div className="flex-1 min-h-0 overflow-y-auto">
                <div className="p-4 border-b border-zinc-800">
                  <h3 className="text-white font-semibold text-sm">{track.title}</h3>
                </div>
                {track.courseContent.map((chapter, ci) => (
                  <div key={ci} className="border-b border-zinc-800">
                    <button
                      onClick={() => setExpandedChapter(expandedChapter === ci ? -1 : ci)}
                      className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-zinc-800 transition-colors"
                    >
                      <span className={`text-sm font-medium ${isLocked(ci) ? "text-zinc-600" : "text-zinc-300"}`}>
                        {chapter.name}
                      </span>
                      <span className="text-zinc-600 text-xs ml-2">
                        {isLocked(ci) ? "🔒" : expandedChapter === ci ? "▲" : "▼"}
                      </span>
                    </button>

                    {expandedChapter === ci && (
                      <div>
                        {chapter.subchapters.map((sub, si) => (
                          <button
                            key={si}
                            onClick={() => handleSelectSub(ci, si)}
                            disabled={isLocked(ci)}
                            className={`w-full px-6 py-2 text-left text-xs transition-colors ${
                              activeChapter === ci && activeSub === si
                                ? `${track.theme} font-semibold bg-zinc-800`
                                : isLocked(ci)
                                ? "text-zinc-700 cursor-not-allowed"
                                : "text-zinc-400 hover:text-white hover:bg-zinc-800"
                            }`}
                          >
                            {sub.name}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {railTab === "tutor" && tutorFloating && (
              <div className="flex-1 flex flex-col items-center justify-center gap-3 px-6 text-center">
                <p className="text-sm text-zinc-400">The tutor is floating over the page.</p>
                <button onClick={() => setTutorFloating(false)}
                        className="text-sm text-indigo-200 border border-indigo-500/40 rounded-lg px-4 py-2 hover:bg-indigo-600/15">
                  Dock it here
                </button>
              </div>
            )}

            {railTab === "lab" && aiCourse && (
              <div className="flex-1 min-h-0 overflow-y-auto p-4">
                {isUserLoggedIn ? (
                  <LabStudio studentId={userId} courseId={aiCourse.course_id} onClose={() => setRailTab("chapters")} />
                ) : (
                  <p className="text-sm text-zinc-400 text-center mt-10">Sign in to quiz yourself on this course.</p>
                )}
              </div>
            )}

            {aiCourse && (
              <PlayerTutor course={aiCourse} userId={userId} lectureTitle={currentSub?.name || track.title}
                           floating={tutorFloating} visible={railTab === "tutor" && !tutorFloating}
                           onPopOut={() => { setTutorFloating(true); setRailTab("chapters"); }}
                           onDock={() => { setTutorFloating(false); setRailTab("tutor"); }}
                           onNavigate={(n) => jumpToRef.current(n)}
                           canJump={(n) => resolveJump(track.courseContent, n.lecture_title, isLocked) !== null}
                           getPosition={() => (videoRef.current && !Number.isNaN(videoRef.current.currentTime)
                             ? videoRef.current.currentTime : undefined)} />
            )}
          </div>
        </aside>
      </div>

    </div>
  );
}
