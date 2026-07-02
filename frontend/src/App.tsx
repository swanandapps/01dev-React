import { BrowserRouter, Routes, Route } from "react-router-dom";
import { useEffect } from "react";
import {
  onAuthStateChanged,
  auth,
  FBisNewUser,
  FBNewSignup,
  FBgetLoggedUserandStoreHistory,
} from "./lib/firebase";
import { useUserSessionStore } from "./store/userSession";
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
import NotesQuizPage from "./pages/NotesQuizPage";

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
        if (history) {
          setCurrentUserHistory(history, isNew ? "new" : "existing", true);
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
      <Route path="/notes-quiz" element={<NotesQuizPage />} />
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
