import { useNavigate } from "react-router-dom";
import Header from "../components/Home/Header";
import Footer from "../components/Home/Footer";

const BLOGS = [
  {
    id: 1,
    title: "Why V8's Hidden Classes Matter for Performance",
    excerpt: "Every time you add a property to an object in JavaScript, V8 is making decisions that affect your app's performance...",
    date: "2024-01-15",
    readTime: "8 min read",
    tag: "V8 Engine",
  },
  {
    id: 2,
    title: "Understanding JavaScript's Prototype Chain",
    excerpt: "The prototype chain is one of JavaScript's most powerful features, yet also one of the most misunderstood...",
    date: "2024-01-10",
    readTime: "10 min read",
    tag: "JavaScript",
  },
  {
    id: 3,
    title: "Building Real-Time Systems: WebSocket Deep Dive",
    excerpt: "WebSockets are not magic. Understanding the handshake, framing, and connection lifecycle changes how you build...",
    date: "2024-01-05",
    readTime: "12 min read",
    tag: "Real-Time",
  },
  {
    id: 4,
    title: "ES Modules vs CommonJS: The Complete Guide",
    excerpt: "The module system in JavaScript evolved from IIFE patterns to CommonJS to ES Modules. Each step had a reason...",
    date: "2023-12-20",
    readTime: "9 min read",
    tag: "Modules",
  },
];

export default function BlogsPage() {
  const navigate = useNavigate();

  return (
    <div className="bg-zinc-950 text-[#F0F0F0] min-h-screen">
      <Header />
      <div className="pt-24 pb-16 px-6 max-w-5xl mx-auto">
        <h1 className="text-4xl font-bold text-white mb-2">Blogs</h1>
        <p className="text-zinc-400 mb-12">Deep dives, first principles, and engineering insights.</p>

        <div className="space-y-6">
          {BLOGS.map((blog) => (
            <article
              key={blog.id}
              onClick={() => navigate(`/blogs/${blog.id}`)}
              className="cursor-pointer bg-zinc-900 border border-zinc-800 rounded-2xl p-6 hover:border-zinc-600 transition-all"
            >
              <div className="flex items-center gap-3 mb-3">
                <span className="text-xs bg-zinc-800 text-zinc-400 px-2 py-1 rounded-full">
                  {blog.tag}
                </span>
                <span className="text-zinc-600 text-xs">{blog.date}</span>
                <span className="text-zinc-600 text-xs">·</span>
                <span className="text-zinc-600 text-xs">{blog.readTime}</span>
              </div>
              <h2 className="text-xl font-semibold text-white mb-2 hover:text-zinc-200">
                {blog.title}
              </h2>
              <p className="text-zinc-400 text-sm leading-relaxed">{blog.excerpt}</p>
            </article>
          ))}
        </div>
      </div>
      <Footer />
    </div>
  );
}
