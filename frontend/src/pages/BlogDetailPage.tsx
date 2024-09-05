import { useParams, Link, Navigate } from "react-router-dom";
import Header from "../components/Home/Header";
import Footer from "../components/Home/Footer";

const BLOGS = [
  {
    id: 1,
    title: "Why V8's Hidden Classes Matter for Performance",
    tag: "V8 Engine",
    date: "January 15, 2024",
    readTime: "8 min read",
    body: `Every time you add a property to an object in JavaScript, V8 is making decisions that affect your app's performance. Those decisions revolve around something called hidden classes.

## What are hidden classes?

V8 doesn't treat JavaScript objects like hash maps at runtime — that would be too slow. Instead, it creates internal structures called "hidden classes" (also called "shapes" or "maps") that describe the layout of an object's properties. Objects that share the same shape share the same hidden class, which lets V8 store their property values in a fixed-offset array rather than looking them up by key.

## The performance implication

When you always add properties in the same order, objects share a hidden class. V8 can use inline caches to access those properties in nanoseconds. The moment you add properties in different orders across objects of the same "type", V8 creates separate hidden classes — and your inline caches go megamorphic. A monomorphic inline cache is 10–100× faster than a megamorphic one.

## What breaks it

\`\`\`js
// Creates two different hidden classes — bad
function Point(x, y) {
  this.x = x;
  this.y = y;
}
const p1 = new Point(1, 2);
p1.z = 3; // adds z after construction — shape transition

// Delete also breaks it
delete p1.x;
\`\`\`

## The fix

Initialize all properties in the constructor, in the same order, every time. Don't add or delete properties after construction. This is one of the reasons TypeScript classes tend to be faster — the structure is known statically.`,
  },
  {
    id: 2,
    title: "Understanding JavaScript's Prototype Chain",
    tag: "JavaScript",
    date: "January 10, 2024",
    readTime: "10 min read",
    body: `The prototype chain is one of JavaScript's most powerful features — and one of the most misunderstood. Most developers use it through class syntax without ever touching it directly. That's fine until you need to debug a property lookup, extend a built-in, or understand why \`instanceof\` sometimes lies.

## How it actually works

Every JavaScript object has an internal \`[[Prototype]]\` slot that points to another object (or null). When you access a property, the engine walks this chain until it either finds the property or hits null.

\`\`\`js
const obj = { a: 1 };
// obj.__proto__ → Object.prototype → null
console.log(obj.toString()); // found on Object.prototype
\`\`\`

## Constructor functions and .prototype

When you write \`new Foo()\`, V8 creates a new object, sets its \`[[Prototype]]\` to \`Foo.prototype\`, then runs \`Foo\` with \`this\` bound to that object.

\`\`\`js
function Animal(name) {
  this.name = name;
}
Animal.prototype.speak = function() {
  return \`\${this.name} speaks\`;
};

const dog = new Animal("Rex");
dog.speak(); // walks chain to Animal.prototype
\`\`\`

## Why this matters for libraries

jQuery, Lodash and every major JavaScript library that predates ES6 used prototype manipulation to attach methods. Understanding the chain lets you read their source code — which is exactly what we do in the Build a Custom Library track.`,
  },
  {
    id: 3,
    title: "Building Real-Time Systems: WebSocket Deep Dive",
    tag: "Real-Time",
    date: "January 5, 2024",
    readTime: "12 min read",
    body: `WebSockets are not magic. The browser API makes them feel trivial — \`new WebSocket(url)\` — but underneath there's a handshake, a framing protocol, and a connection lifecycle that every real-time system engineer needs to understand.

## The handshake

A WebSocket connection starts as a regular HTTP request with an Upgrade header. The server responds with 101 Switching Protocols. The key exchange uses a base64-encoded SHA-1 of the client's nonce + a fixed GUID, which proves the server understood the upgrade.

\`\`\`
Client → GET /ws HTTP/1.1
         Upgrade: websocket
         Connection: Upgrade
         Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==

Server → HTTP/1.1 101 Switching Protocols
         Upgrade: websocket
         Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
\`\`\`

## Framing

After the handshake, both sides communicate in frames. Each frame has an opcode (text, binary, ping, pong, close), a masking bit (client→server frames are always masked), a payload length, and the payload. The masking key is a random 4-byte XOR mask to prevent proxy cache poisoning.

## Why this matters

When you know the framing format, you can parse WebSocket traffic in Wireshark, build your own server from raw TCP sockets, diagnose why large payloads behave differently, and understand what \`ws\` and \`socket.io\` are actually doing underneath.`,
  },
  {
    id: 4,
    title: "ES Modules vs CommonJS: The Complete Guide",
    tag: "Modules",
    date: "December 20, 2023",
    readTime: "9 min read",
    body: `The module system in JavaScript evolved from IIFE patterns to CommonJS to ES Modules. Each step had a reason. Understanding the full arc helps you make better architecture decisions and explains why certain tools behave the way they do.

## IIFE — the original module pattern

Before any module system existed, developers used Immediately Invoked Function Expressions to scope code:

\`\`\`js
const MyLib = (function() {
  const private = "hidden";
  return { public: () => private };
})();
\`\`\`

Functions create scope in JavaScript. The IIFE was the only tool available. This is still widely used inside browser libraries today.

## CommonJS — Node's solution

Node.js needed a synchronous module system for the filesystem. \`require()\` is synchronous and returns a cached module object. Exports are mutable — you can \`require\` a module and then modify its exports, and other requirers see the change.

\`\`\`js
// module.js
module.exports = { value: 1 };

// main.js
const mod = require('./module');
\`\`\`

## ES Modules — the native standard

ESM was designed for static analysis. Imports and exports are declared at the top level and cannot be conditional. This lets bundlers tree-shake and engines build dependency graphs before executing code.

\`\`\`js
import { value } from './module.js';
export const doubled = value * 2;
\`\`\`

The key difference: ESM bindings are live. If a module changes its exported value, all importers see the new value immediately. CommonJS gives you a copy at require-time.`,
  },
];

export default function BlogDetailPage() {
  const { id } = useParams<{ id: string }>();
  const blog = BLOGS.find((b) => b.id === Number(id));

  if (!blog) return <Navigate to="/blogs" replace />;

  return (
    <div className="bg-zinc-950 text-[#F0F0F0] min-h-screen">
      <Header />
      <div className="pt-24 pb-16 px-6">
        <div className="max-w-2xl mx-auto">
          <Link to="/blogs" className="text-zinc-500 hover:text-white text-sm transition-colors flex items-center gap-1.5 mb-10">
            ← All blogs
          </Link>

          <div className="flex items-center gap-3 mb-6">
            <span className="text-xs bg-zinc-800 border border-zinc-700 text-zinc-400 px-2.5 py-1 rounded-full">
              {blog.tag}
            </span>
            <span className="text-zinc-600 text-xs">{blog.date}</span>
            <span className="text-zinc-600 text-xs">·</span>
            <span className="text-zinc-600 text-xs">{blog.readTime}</span>
          </div>

          <h1 className="text-4xl font-bold text-white mb-10 leading-tight">{blog.title}</h1>

          <div className="prose-zinc">
            {blog.body.split("\n\n").map((block, i) => {
              if (block.startsWith("## ")) {
                return (
                  <h2 key={i} className="text-xl font-bold text-white mt-10 mb-4">
                    {block.slice(3)}
                  </h2>
                );
              }
              if (block.startsWith("```")) {
                const lines = block.split("\n");
                const code = lines.slice(1, lines.length - 1).join("\n");
                return (
                  <pre key={i} className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 my-6 overflow-x-auto">
                    <code className="text-zinc-300 text-sm font-mono leading-relaxed">{code}</code>
                  </pre>
                );
              }
              return (
                <p key={i} className="text-zinc-400 leading-relaxed mb-5">
                  {block}
                </p>
              );
            })}
          </div>

          <div className="mt-16 pt-8 border-t border-zinc-800">
            <p className="text-zinc-500 text-sm mb-4">Want to go deeper?</p>
            <Link
              to="/tracks"
              className="inline-flex items-center gap-2 bg-white text-black px-5 py-2.5 rounded-xl font-semibold text-sm hover:bg-zinc-100 transition-colors"
            >
              Explore Tracks →
            </Link>
          </div>
        </div>
      </div>
      <Footer />
    </div>
  );
}
