import { Link } from "react-router-dom";
import { Lock } from "lucide-react";
import type { ReactNode } from "react";

/**
 * Shown to signed-out users in place of a gated feature. Gives a glimpse of what
 * the feature is (icon, tagline, a small sample preview) and prompts sign-in.
 */
export function FeatureGlimpse({
  icon: Icon,
  title,
  tagline,
  bullets,
  sample,
}: {
  icon: typeof Lock;
  title: string;
  tagline: string;
  bullets: string[];
  sample?: ReactNode;
}) {
  return (
    <div className="flex items-center justify-center min-h-[calc(100vh-4rem)] px-6 py-10">
      <div className="max-w-md w-full bg-zinc-900 border border-zinc-800 rounded-2xl p-7 text-center">
        <div className="w-14 h-14 rounded-2xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center mx-auto mb-5">
          <Icon className="w-7 h-7 text-indigo-400" />
        </div>
        <h2 className="text-xl font-semibold text-zinc-100 mb-2">{title}</h2>
        <p className="text-sm text-zinc-400 mb-5 leading-relaxed">{tagline}</p>

        {sample && (
          <div className="relative mb-5">
            <div className="pointer-events-none select-none">{sample}</div>
            <div className="absolute inset-0 bg-gradient-to-t from-zinc-900 via-zinc-900/30 to-transparent" />
          </div>
        )}

        <ul className="text-left space-y-2 mb-6">
          {bullets.map((b) => (
            <li key={b} className="flex items-start gap-2 text-sm text-zinc-300">
              <span className="text-indigo-400 mt-0.5">✓</span>
              <span>{b}</span>
            </li>
          ))}
        </ul>

        <Link
          to="/signin"
          className="flex items-center justify-center gap-2 w-full bg-white text-black font-semibold rounded-xl py-3 hover:bg-zinc-100 transition-colors"
        >
          <Lock className="w-4 h-4" />
          Sign in to unlock
        </Link>
        <p className="text-xs text-zinc-600 mt-3">Free with your Google account</p>
      </div>
    </div>
  );
}
