import { useNavigate } from "react-router-dom";
import { useUserSessionStore } from "../../store/userSession";
import {
  auth,
  googleProvider,
  signInWithPopup,
  FBisNewUser,
  FBNewSignup,
  FBgetLoggedUserandStoreHistory,
} from "../../lib/firebase";

export default function SignIn() {
  const navigate = useNavigate();
  const { setCurrentUser, setCurrentUserHistory, setSigsinInProgress } = useUserSessionStore();

  const handleGoogleSignIn = async () => {
    setSigsinInProgress(true);
    try {
      const result = await signInWithPopup(auth, googleProvider);
      const user = result.user;

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

      navigate("/tracks");
    } catch (err) {
      console.error("Sign in error:", err);
    } finally {
      setSigsinInProgress(false);
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 flex">
      <div className="hidden lg:flex lg:w-1/2 relative">
        <video
          autoPlay
          muted
          loop
          playsInline
          className="absolute inset-0 w-full h-full object-cover opacity-60"
          src="https://firebasestorage.googleapis.com/v0/b/topdev-93530.appspot.com/o/Website%20utils%2FBCL%20Trailer%20.mp4?alt=media&token=ec2dfe29-e0d1-4050-bb49-83df014c994f"
        />
        <div className="absolute inset-0 bg-zinc-950/50" />
        <div className="relative z-10 p-12 flex flex-col justify-end">
          <h2 className="text-4xl font-bold text-white mb-4">
            Join the top<br />0.1% developers.
          </h2>
          <p className="text-zinc-400 text-lg">
            Deep-dive courses. First principles. Real projects.
          </p>
        </div>
      </div>

      <div className="w-full lg:w-1/2 flex items-center justify-center px-8">
        <div className="w-full max-w-md">
          <h1 className="text-3xl font-bold text-white mb-2">Welcome back</h1>
          <p className="text-zinc-400 mb-10">Sign in to access your courses.</p>

          <button
            onClick={handleGoogleSignIn}
            className="w-full flex items-center justify-center gap-3 bg-white text-black py-4 rounded-xl font-semibold hover:bg-zinc-200 transition-colors"
          >
            <svg width="20" height="20" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
            Continue with Google
          </button>

          <p className="text-zinc-600 text-xs text-center mt-8">
            By continuing, you agree to our Terms of Service and Privacy Policy.
          </p>
        </div>
      </div>
    </div>
  );
}
