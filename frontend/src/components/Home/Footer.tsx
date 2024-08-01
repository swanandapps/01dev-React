import { Link } from "react-router-dom";

const TRACKS = [
  { id: 2, label: "Build a Custom Library" },
  { id: 5, label: "Build a State Manager" },
  { id: 6, label: "Build a Web Framework" },
  { id: 7, label: "JavaScript Engine Internals" },
  { id: 8, label: "Build a Real-Time System" },
];

export default function Footer() {
  return (
    <footer className="bg-zinc-950 border-t border-zinc-800">
      <div className="max-w-7xl mx-auto px-6 py-16">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-10 mb-12">
          {/* Brand */}
          <div className="md:col-span-1">
            <h3 className="text-white font-bold text-lg mb-3">0.1% DEV</h3>
            <p className="text-zinc-500 text-sm leading-relaxed mb-5">
              Engineering courses that go all the way down. Build the tools that other developers use.
            </p>
            <div className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-green-400" />
              <span className="text-zinc-500 text-xs">Actively maintained</span>
            </div>
          </div>

          {/* Tracks */}
          <div>
            <h4 className="text-zinc-300 font-semibold text-sm mb-4">Tracks</h4>
            <ul className="space-y-2.5">
              {TRACKS.map((t) => (
                <li key={t.id}>
                  <Link
                    to={`/coursedetails/${t.id}`}
                    className="text-zinc-500 hover:text-white text-sm transition-colors"
                  >
                    {t.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Platform */}
          <div>
            <h4 className="text-zinc-300 font-semibold text-sm mb-4">Platform</h4>
            <ul className="space-y-2.5">
              {[
                { to: "/tracks", label: "All Tracks" },
                { to: "/research", label: "Research" },
                { to: "/blogs", label: "Blogs" },
                { to: "/maps", label: "Knowledge Maps" },
                { to: "/ask", label: "AI Assistant" },
              ].map((l) => (
                <li key={l.to}>
                  <Link to={l.to} className="text-zinc-500 hover:text-white text-sm transition-colors">
                    {l.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Company */}
          <div>
            <h4 className="text-zinc-300 font-semibold text-sm mb-4">Company</h4>
            <ul className="space-y-2.5">
              {[
                { to: "/blogs", label: "Contact" },
                { to: "/blogs", label: "Privacy Policy" },
                { to: "/blogs", label: "Terms of Service" },
              ].map((l) => (
                <li key={l.label}>
                  <Link to={l.to} className="text-zinc-500 hover:text-white text-sm transition-colors">
                    {l.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="border-t border-zinc-800 pt-8 flex flex-col sm:flex-row items-center justify-between gap-4">
          <p className="text-zinc-600 text-sm">
            © {new Date().getFullYear()} 0.1% DEV. All rights reserved.
          </p>
          <p className="text-zinc-700 text-xs">
            Built for engineers who want to understand how things actually work.
          </p>
        </div>
      </div>
    </footer>
  );
}
