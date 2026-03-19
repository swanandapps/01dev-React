import { useNavigate } from "react-router-dom";
import tracks from "../../data/tracks";

export default function TracksList() {
  const navigate = useNavigate();

  return (
    <section className="py-20 px-6 bg-zinc-950 min-h-screen">
      <div className="max-w-7xl mx-auto">
        <div className="mb-14">
          <p className="text-indigo-400 text-sm font-semibold uppercase tracking-widest mb-3">All Tracks</p>
          <h1 className="text-5xl font-bold text-white mb-4 leading-tight">
            Pick something hard.
          </h1>
          <p className="text-zinc-400 text-lg max-w-xl">
            Every track ends with a real, shippable project. No certificates — just code that proves you understand.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {tracks.map((track) => (
            <div
              key={track.id}
              onClick={() => navigate(`/coursedetails/${track.id}`)}
              className="cursor-pointer group bg-zinc-900 border border-zinc-800 hover:border-zinc-600 rounded-2xl overflow-hidden transition-all hover:scale-[1.02] hover:bg-zinc-800/50"
            >
              {/* Colour strip + trailer */}
              <div className="relative h-44 overflow-hidden bg-zinc-800">
                {track.trailer && (
                  <video
                    autoPlay
                    muted
                    loop
                    playsInline
                    className="absolute inset-0 w-full h-full object-cover opacity-50 group-hover:opacity-70 transition-opacity"
                    src={track.trailer}
                  />
                )}
                <div className="absolute inset-0 bg-gradient-to-t from-zinc-900 via-transparent to-transparent" />
                <div className="absolute bottom-3 left-4 right-4 flex items-center justify-between">
                  <span className={`text-xs font-bold uppercase tracking-widest ${track.theme}`}>
                    {track.id === 2 ? "Build · Ship · Own" :
                     track.id === 1 ? "Language Design" :
                     track.id === 5 ? "Reactivity" :
                     track.id === 6 ? "Framework Internals" :
                     track.id === 7 ? "V8 Internals" :
                     track.id === 8 ? "Real-Time Systems" :
                     "Engineering"}
                  </span>
                </div>
              </div>

              {/* Info */}
              <div className="p-5">
                <h3 className="text-white font-semibold text-lg mb-2 group-hover:text-zinc-100">
                  {track.title}
                </h3>
                <p className="text-zinc-500 text-sm leading-relaxed line-clamp-2">
                  {track.description.length > 120 ? track.description.slice(0, 120) + "…" : track.description}
                </p>

                {track.modules.length > 0 && (
                  <div className="mt-4 flex items-center gap-4 text-xs text-zinc-600">
                    <span>{track.modules.length} modules</span>
                    <span>·</span>
                    <span>{track.courseContent.length} chapters</span>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
