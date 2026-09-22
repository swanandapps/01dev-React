import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useEffect } from "react";
import {
  onAuthStateChanged,
  auth,
  FBisNewUser,
  FBNewSignup,
  FBgetLoggedUserandStoreHistory,
} from "./lib/firebase";
import { useUserSessionStore } from "./store/userSession";
import { getEnrollment } from "./lib/learnApi";
import HomePage from "./pages/HomePage";
import TracksPage from "./pages/TracksPage";
import CourseDetailsPage from "./pages/CourseDetailsPage";
import CoursePlayerPage from "./pages/CoursePlayerPage";
import SignInPage from "./pages/SignInPage";
import ProfilePage from "./pages/ProfilePage";
import BlogsPage from "./pages/BlogsPage";
import BlogDetailPage from "./pages/BlogDetailPage";
import AskPage from "./pages/AskPage";
import LearnPage from "./pages/LearnPage";
import LabPage from "./pages/LabPage";

function AppInner() {
  const {
    setCurrentUser,
    setCurrentUserHistory,
    setCurrentuserCountry,
    setIsLoading,
    logout,
  } = useUserSessionStore();

  useEffect(() => {
    fetch("https://ipapi.co/json/")
      .then((r) => r.json())
      .then((data) => {
        if (data.country_name) {
          setCurrentuserCountry(data.country_name);
        }
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    const unsub = onAuthStateChanged(auth, async (user) => {
      if (user) {
        setCurrentUser({
          uid: user.uid,
          displayName: user.displayName,
          email: user.email,
          photoURL: user.photoURL,
        });
        const isNew = await FBisNewUser(user.uid);
        if (isNew) {
          await FBNewSignup({
            uid: user.uid,
            displayName: user.displayName,
            email: user.email,
            photoURL: user.photoURL,
          });
        }
        const history = await FBgetLoggedUserandStoreHistory(user.uid);
        // Enrollment (PrevCourses) is Postgres now, not Firestore — Firebase
        // stays scoped to auth + storage. Fall back to Firestore's cached
        // PrevCourses only if the enrollment fetch itself fails.
        let prevCourses: { id: number }[] = (history as { PrevCourses?: { id: number }[] } | null)?.PrevCourses || [];
        try {
          const enrollment = await getEnrollment(user.uid);
          prevCourses = enrollment.map((c) => ({ id: c.id }));
        } catch (e) {
          console.error("Enrollment fetch failed, falling back to cached Firestore data", e);
        }
        if (history || prevCourses.length) {
          setCurrentUserHistory({ ...(history || {}), PrevCourses: prevCourses }, isNew ? "new" : "existing", true);
        }
      } else {
        logout();
      }
      setIsLoading(false);
    });
    return unsub;
  }, []);

  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/tracks" element={<TracksPage />} />
      <Route path="/coursedetails/:courseid" element={<CourseDetailsPage />} />
      <Route path="/course/:courseid" element={<CoursePlayerPage />} />
      <Route path="/signin" element={<SignInPage />} />
      <Route path="/profile" element={<ProfilePage />} />
      <Route path="/blogs" element={<BlogsPage />} />
      <Route path="/blogs/:id" element={<BlogDetailPage />} />
      <Route path="/ask" element={<AskPage />} />
      <Route path="/dashboard" element={<LearnPage />} />
      <Route path="/lab" element={<LabPage />} />
      {/* keep the old path working for anyone with a bookmark */}
      <Route path="/quizme" element={<Navigate to="/lab" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppInner />
    </BrowserRouter>
  );
}
