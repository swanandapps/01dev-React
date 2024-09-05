import { useNavigate } from "react-router-dom";
import Header from "../components/Home/Header";
import { useUserSessionStore } from "../store/userSession";
import { auth, signOut } from "../lib/firebase";
import tracks from "../data/tracks";

export default function ProfilePage() {
  const { currentuser, currentuserhistory, logout, isUserLoggedIn } = useUserSessionStore();
  const navigate = useNavigate();

  if (!isUserLoggedIn) {
    navigate("/signin");
    return null;
  }

  const user = currentuser as { displayName?: string; email?: string; photoURL?: string };
  const history = currentuserhistory as { PrevCourses?: { id: number }[] };
  const boughtCourses = history?.PrevCourses || [];

  const handleSignOut = async () => {
    await signOut(auth);
    logout();
    navigate("/");
  };

  return (
    <div className="bg-zinc-950 text-[#F0F0F0] min-h-screen">
      <Header />
      <div className="pt-24 pb-16 px-6 max-w-3xl mx-auto">
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-8 mb-8">
          <div className="flex items-center gap-6">
            {user.photoURL && (
              <img src={user.photoURL} alt="Profile" className="w-16 h-16 rounded-full" />
            )}
            <div>
              <h1 className="text-2xl font-bold text-white">{user.displayName}</h1>
              <p className="text-zinc-400">{user.email}</p>
            </div>
          </div>
        </div>

        <div className="mb-8">
          <h2 className="text-xl font-semibold text-white mb-4">My Courses</h2>
          {boughtCourses.length === 0 ? (
            <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-8 text-center">
              <p className="text-zinc-500 mb-4">You haven't purchased any courses yet.</p>
              <button
                onClick={() => navigate("/tracks")}
                className="bg-white text-black px-6 py-2 rounded-xl font-semibold hover:bg-zinc-200"
              >
                Explore Tracks
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {boughtCourses.map(({ id }) => {
                const track = tracks.find((t) => t.id === id);
                if (!track) return null;
                return (
                  <div
                    key={id}
                    onClick={() => navigate(`/course/${id}`)}
                    className={`cursor-pointer bg-zinc-900 border ${track.border} rounded-xl p-4 hover:scale-[1.02] transition-transform`}
                  >
                    <h3 className={`font-semibold ${track.theme} mb-1`}>{track.title}</h3>
                    <p className="text-zinc-500 text-xs">Tap to continue →</p>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <button
          onClick={handleSignOut}
          className="bg-zinc-800 text-zinc-400 hover:text-white px-6 py-3 rounded-xl font-medium hover:bg-zinc-700 transition-colors"
        >
          Sign Out
        </button>
      </div>
    </div>
  );
}
