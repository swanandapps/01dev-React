import Header from "../components/Home/Header";
import Footer from "../components/Home/Footer";

const RESEARCH_VIDEOS = [
  {
    id: 1,
    title: "V8 Hidden Classes Explained",
    description: "A deep dive into how V8 creates hidden classes for performance optimization.",
    src: "https://firebasestorage.googleapis.com/v0/b/topdev-93530.appspot.com/o/Research%2F1.mp4?alt=media&token=researchvideo1",
    thumbnail: "",
  },
  {
    id: 2,
    title: "WebSocket Internals",
    description: "Understanding the WebSocket protocol at the wire level.",
    src: "https://firebasestorage.googleapis.com/v0/b/topdev-93530.appspot.com/o/Research%2F2.mp4?alt=media&token=researchvideo2",
    thumbnail: "",
  },
];

export default function ResearchPage() {
  return (
    <div className="bg-zinc-950 text-[#F0F0F0] min-h-screen">
      <Header />
      <div className="pt-24 pb-16 px-6 max-w-7xl mx-auto">
        <h1 className="text-4xl font-bold text-white mb-2">Research</h1>
        <p className="text-zinc-400 mb-12">
          Deep dives into engineering internals.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          {RESEARCH_VIDEOS.map((video) => (
            <div key={video.id} className="bg-zinc-900 rounded-2xl border border-zinc-800 overflow-hidden">
              <div className="aspect-video bg-zinc-800">
                <video
                  controls
                  className="w-full h-full object-cover"
                  src={video.src}
                  poster={video.thumbnail}
                >
                  Your browser does not support the video tag.
                </video>
              </div>
              <div className="p-6">
                <h3 className="text-white font-semibold text-lg mb-2">{video.title}</h3>
                <p className="text-zinc-400 text-sm">{video.description}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
      <Footer />
    </div>
  );
}
