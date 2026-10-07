import { useParams, Navigate, useSearchParams } from "react-router-dom";
import { useState, useRef, useEffect } from "react";
import Header from "../components/Home/Header";
import tracks from "../data/tracks";
import { useUserSessionStore } from "../store/userSession";
import { decodeVideoUrl } from "../lib/videoDecoder";
import { recordLectureView, getCourses, getLectureMoments, viewedLectures } from "../lib/learnApi";
import type { LectureMoment } from "../lib/learnApi";
import type { OutputType } from "../lib/labApi";
import { FlaskConical, Layers, Check, ChevronLeft, ListVideo } from "lucide-react";
import { LabStudio } from "../components/lab/LabStudio";
import { PlayerTutor } from "../components/learn/PlayerTutor";
import { QuickQuiz } from "../components/learn/QuickQuiz";
import { resolveJump } from "../lib/lectureMatch";
import type { TutorNavigate } from "../lib/learnApi";
import type { Course } from "../types/learn";

export default function CoursePlayerPage() {
  const { courseid } = useParams<{ courseid: string }>();
  const [searchParams] = useSearchParams();
  const { isCourseBought, currentuser, isUserLoggedIn } = useUserSessionStore();
  const userId = (currentuser?.uid as string) || "anonymous";
  // Layout E: course outline (left, collapsible) · video + key moments + practice (centre) · tutor (right, always on).
  const [outlineOpen, setOutlineOpen] = useState(true);
  const [tutorFloating, setTutorFloating] = useState(false);
  const [labOutputs, setLabOutputs] = useState<OutputType[] | null>(null); // open = Lab on this lecture (flashcards)
  const [quizAt, setQuizAt] = useState<number | null>(null);                // open = quick quiz, video position
  const [moments, setMoments] = useState<LectureMoment[]>([]);
  const [nowIdx, setNowIdx] = useState(-1);

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

  // Key moments for the lecture on screen (owners only; quietly empty otherwise).
  useEffect(() => {
    setMoments([]);
    setNowIdx(-1);
    if (!aiCourse || !currentSub?.name || !bought || !isUserLoggedIn) return;
    let cancelled = false;
    getLectureMoments(aiCourse.course_id, currentSub.name)
      .then((ms) => { if (!cancelled) setMoments(ms); })
      .catch(() => { /* no moments row */ });
    return () => { cancelled = true; };
  }, [aiCourse, currentSub?.name, bought, isUserLoggedIn]);

  const onTimeUpdate = () => {
    const t = videoRef.current?.currentTime ?? 0;
    let i = -1;
    moments.forEach((m, k) => { if (m.start_time <= t) i = k; });
    if (i !== nowIdx) setNowIdx(i);
  };

  const seekTo = (seconds: number) => {
    const v = videoRef.current;
    if (!v) return;
    v.currentTime = seconds;
    v.play().catch(() => {});
  };

  const viewed = viewedLectures();
  const allLectures = track.courseContent.flatMap((c) => c.subchapters.map((sc) => sc.name));
  const watchedCount = allLectures.filter((n) => viewed.has(n)).length;
  const mmss = (t: number) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;

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

  const outline = (
    <nav aria-label="Course outline"
         className={`order-3 lg:order-1 flex-shrink-0 border-t lg:border-t-0 lg:border-r border-zinc-800 bg-zinc-950 flex flex-col min-h-0 ${
           outlineOpen ? "w-full lg:w-[264px]" : "w-full lg:w-12"}`}>
      {outlineOpen ? (
        <>
          <div className="px-4 py-3.5 border-b border-zinc-800 flex flex-col gap-2 flex-shrink-0">
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-bold text-white truncate">{track.title}</span>
              <button onClick={() => setOutlineOpen(false)} aria-label="Collapse outline"
                      className="hidden lg:flex w-7 h-7 rounded-md text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 items-center justify-center">
                <ChevronLeft className="w-4 h-4" />
              </button>
            </div>
            <div className="h-1 bg-zinc-800 rounded"><div className="h-1 bg-violet-400 rounded" style={{ width: `${allLectures.length ? (100 * watchedCount) / allLectures.length : 0}%` }} /></div>
            <span className="text-[11px] text-zinc-400">{watchedCount} of {allLectures.length} lectures opened</span>
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto py-1.5">
            {track.courseContent.map((chapter, ci) => {
              const done = chapter.subchapters.length > 0 && chapter.subchapters.every((sc) => viewed.has(sc.name));
              return (
                <div key={ci}>
                  <button
                    onClick={() => setExpandedChapter(expandedChapter === ci ? -1 : ci)}
                    aria-expanded={expandedChapter === ci}
                    className={`w-full flex items-center gap-2 px-4 py-2 text-left text-[13px] hover:bg-zinc-900 ${
                      activeChapter === ci ? "text-white font-semibold" : isLocked(ci) ? "text-zinc-600" : "text-zinc-300"}`}
                  >
                    {isLocked(ci) ? <span aria-hidden="true" className="w-3.5 text-[10px]">🔒</span>
                      : done ? <Check className="w-3.5 h-3.5 text-green-500 flex-shrink-0" />
                      : <span className="w-3.5 flex-shrink-0" />}
                    <span className="truncate">{chapter.name.replace(/^Chapter\s+/, "")}</span>
                  </button>
                  {expandedChapter === ci && chapter.subchapters.map((sub, si) => (
                    <button
                      key={si}
                      onClick={() => handleSelectSub(ci, si)}
                      disabled={isLocked(ci)}
                      className={`w-full pl-10 pr-4 py-1.5 text-left text-xs transition-colors ${
                        activeChapter === ci && activeSub === si
                          ? "text-white bg-violet-500/10 border-l-2 border-violet-400"
                          : isLocked(ci) ? "text-zinc-700 cursor-not-allowed"
                          : viewed.has(sub.name) ? "text-zinc-500 hover:text-white hover:bg-zinc-900"
                          : "text-zinc-400 hover:text-white hover:bg-zinc-900"}`}
                    >
                      {sub.name}
                    </button>
                  ))}
                </div>
              );
            })}
          </div>
        </>
      ) : (
        <button onClick={() => setOutlineOpen(true)} aria-label="Show course outline"
                className="m-2 w-8 h-8 rounded-md text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 flex items-center justify-center">
          <ListVideo className="w-4 h-4" />
        </button>
      )}
    </nav>
  );

  return (
    <div className="bg-zinc-950 text-[#F0F0F0] min-h-screen">
      <Header />
      <div className="pt-16 flex flex-col lg:flex-row lg:h-screen">
        {outline}

        <main className="order-1 lg:order-2 flex-1 min-w-0 flex flex-col lg:overflow-y-auto">
          <div className="aspect-video w-full bg-black flex-shrink-0">
            {currentSub && !isLocked(activeChapter) ? (
              <video
                ref={videoRef}
                controls
                className="w-full h-full"
                src={getVideoSrc(currentSub.src)}
                onCanPlay={handleCanPlay}
                onTimeUpdate={onTimeUpdate}
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

          <div className="px-6 pt-4 pb-2">
            <h2 className="text-lg font-semibold text-white">{currentSub?.name || "Select a lecture"}</h2>
            <p className="text-zinc-500 text-sm mt-0.5">{track.courseContent[activeChapter]?.name}</p>
          </div>

          {moments.length > 0 && (
            <section aria-label="Key moments" className="pb-3">
              <h3 className="px-6 pt-1 text-[11px] font-bold tracking-widest text-zinc-400">KEY MOMENTS</h3>
              <div className="flex gap-2.5 px-6 pt-2.5 pb-1 overflow-x-auto">
                {moments.map((m, i) => (
                  <button
                    key={m.start_time}
                    onClick={() => seekTo(m.start_time)}
                    className={`w-44 flex-shrink-0 text-left rounded-xl px-3 py-2.5 border transition-colors flex flex-col gap-1.5 ${
                      i === nowIdx ? "bg-violet-500/10 border-violet-500" : "bg-zinc-900 border-zinc-800 hover:border-zinc-600"}`}
                  >
                    <span className={`font-mono text-xs ${i === nowIdx ? "text-violet-300 font-semibold" : "text-zinc-500"}`}>
                      {mmss(m.start_time)}{i === nowIdx ? " · now" : ""}
                    </span>
                    <span className={`text-[13px] leading-snug line-clamp-3 ${i === nowIdx ? "text-white" : "text-zinc-300"}`}>{m.summary}</span>
                  </button>
                ))}
              </div>
            </section>
          )}

          {aiCourse && isUserLoggedIn && currentSub && !isLocked(activeChapter) && (
            <section aria-label="Practice this lecture"
                     className="mx-6 mb-5 mt-1 px-4 py-3.5 rounded-2xl border border-teal-900 bg-teal-950/40 flex flex-wrap items-center gap-3">
              <FlaskConical className="w-5 h-5 text-teal-300 flex-shrink-0" />
              <div className="flex-1 min-w-[180px]">
                <p className="text-sm font-bold text-teal-50">Check yourself on {currentSub.name.split(" - ")[0]}</p>
                <p className="text-xs text-teal-300/90">3 quick questions on what you've watched</p>
              </div>
              <button onClick={() => setQuizAt(videoRef.current?.currentTime ?? 0)}
                      className="bg-teal-500 hover:bg-teal-400 text-teal-950 text-sm font-bold rounded-lg px-4 py-2">
                Quiz me
              </button>
              <button onClick={() => setLabOutputs(["flashcards"])}
                      className="flex items-center gap-1.5 border border-teal-800 text-teal-200 hover:bg-teal-900/40 text-sm rounded-lg px-3 py-2">
                <Layers className="w-4 h-4" /> Flashcards
              </button>
            </section>
          )}
        </main>

        {aiCourse && (
          <aside aria-label="AI tutor"
                 className={tutorFloating
                   ? "contents" /* the floating window is position:fixed; the column itself gives its space to the video */
                   : "order-2 lg:order-3 w-full lg:w-[360px] flex-shrink-0 border-t lg:border-t-0 lg:border-l border-zinc-800 bg-zinc-900 flex flex-col h-[70vh] lg:h-auto min-h-0"}>
            <PlayerTutor course={aiCourse} userId={userId} lectureTitle={currentSub?.name || track.title}
                         floating={tutorFloating} visible={!tutorFloating}
                         onPopOut={() => setTutorFloating(true)}
                         onDock={() => setTutorFloating(false)}
                         onNavigate={(n) => jumpToRef.current(n)}
                         canJump={(n) => resolveJump(track.courseContent, n.lecture_title, isLocked) !== null}
                         getPosition={() => (videoRef.current && !Number.isNaN(videoRef.current.currentTime)
                           ? videoRef.current.currentTime : undefined)} />
          </aside>
        )}
      </div>

      {quizAt !== null && aiCourse && currentSub && (
        <QuickQuiz courseSlug={aiCourse.course_id} lecture={currentSub.name} position={quizAt}
                   onClose={() => setQuizAt(null)} />
      )}

      {labOutputs && aiCourse && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" onClick={() => setLabOutputs(null)}>
          <div className="bg-zinc-900 border border-zinc-700/60 rounded-2xl w-full max-w-xl max-h-[90vh] overflow-y-auto p-6"
               onClick={(e) => e.stopPropagation()}>
            <LabStudio studentId={userId} courseId={aiCourse.course_id} onClose={() => setLabOutputs(null)}
                       initialLectureTitle={currentSub?.name} initialOutputs={labOutputs} autoStart />
          </div>
        </div>
      )}
    </div>
  );
}
