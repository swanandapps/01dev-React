import { Link, useNavigate, useLocation } from "react-router-dom";
import { Home, BookOpen, FileText, Route, Bot, GraduationCap } from "lucide-react";
import { useUserSessionStore } from "../../store/userSession";
import { auth, signOut } from "../../lib/firebase";

const NAV_LINKS = [
  { to: "/", label: "Home", icon: Home, exact: true },
  { to: "/tracks", label: "Tracks", icon: BookOpen, exact: false },
  { to: "/blogs", label: "Blogs", icon: FileText, exact: false },
  { to: "/roadmap", label: "Roadmap", icon: Route, exact: false },
  { to: "/dashboard", label: "Dashboard", icon: GraduationCap, exact: false },
];

export default function Header() {
  const { isUserLoggedIn, currentuser, logout } = useUserSessionStore();
  const navigate = useNavigate();
  const location = useLocation();

  const handleSignOut = async () => {
    await signOut(auth);
    logout();
    navigate("/");
  };

  const user = currentuser as { displayName?: string; photoURL?: string };

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-zinc-950/90 backdrop-blur-md border-b border-zinc-800/60">
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
        {/* Logo */}
        <Link to="/" className="flex items-center gap-2 group">
          <span className="text-white font-bold text-lg tracking-tight group-hover:text-zinc-200 transition-colors">
            0.1% DEV
          </span>
        </Link>

        {/* Nav links */}
        <div className="hidden md:flex items-center gap-1">
          {NAV_LINKS.map(({ to, label, icon: Icon, exact }) => {
            const active = exact
              ? location.pathname === to
              : location.pathname.startsWith(to);
            return (
              <Link
                key={to}
                to={to}
                className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm transition-colors ${
                  active
                    ? "text-white bg-zinc-800"
                    : "text-zinc-400 hover:text-white hover:bg-zinc-800/60"
                }`}
              >
                <Icon size={15} />
                {label}
              </Link>
            );
          })}
          <Link
            to="/ask"
            className={`ml-2 flex items-center gap-1.5 text-sm px-3.5 py-2 rounded-lg font-medium transition-colors ${
              location.pathname === "/ask"
                ? "bg-zinc-200 text-black"
                : "bg-white text-black hover:bg-zinc-100"
            }`}
          >
            <Bot size={15} />
            Ask AI
          </Link>
        </div>

        {/* Auth */}
        <div className="flex items-center gap-3">
          {isUserLoggedIn ? (
            <div className="flex items-center gap-2 bg-zinc-900 border border-zinc-800 rounded-full pl-1 pr-3 py-1">
              {user.photoURL ? (
                <img
                  src={user.photoURL}
                  alt="Profile"
                  className="w-6 h-6 rounded-full flex-shrink-0 cursor-pointer"
                  onClick={() => navigate("/profile")}
                />
              ) : (
                <div className="w-6 h-6 rounded-full bg-zinc-700 flex items-center justify-center text-xs text-white flex-shrink-0">
                  {user.displayName?.[0] ?? "U"}
                </div>
              )}
              <button
                onClick={handleSignOut}
                className="text-zinc-400 hover:text-white text-sm transition-colors leading-none"
              >
                Sign out
              </button>
            </div>
          ) : (
            <Link
              to="/signin"
              className="border border-zinc-600 text-white px-4 py-2 rounded-lg text-sm font-semibold hover:bg-zinc-800 transition-colors"
            >
              Sign In
            </Link>
          )}
        </div>
      </div>
    </nav>
  );
}
