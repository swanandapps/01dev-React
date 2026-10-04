// Exports the course catalog (frontend/src/data/tracks.ts — the source of truth)
// to backend/app/data/catalog.json for the chat's course lookup.
// Usage:  node frontend/scripts/export-catalog.mjs          (write)
//         node frontend/scripts/export-catalog.mjs --check  (exit 1 if stale)
// Node 22 runs .ts imports directly (type stripping); tracks.ts has no imports.
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const tracks = (await import("../src/data/tracks.ts")).default;
const { RAG_COURSE_MAP } = await import("../src/types/rag.ts");
const slugById = Object.fromEntries(Object.entries(RAG_COURSE_MAP).map(([slug, id]) => [id, slug]));

const catalog = tracks.map((t) => ({
  id: t.id,
  slug: slugById[t.id] ?? null,
  title: t.title,
  description: t.description,
  launched: t.launched,
  url: `/course/${t.id}`,
  modules: t.modules.map((m) => ({ title: m.title, description: m.description })),
  chapters: t.courseContent.map((c) => ({ name: c.name, subchapters: c.subchapters.map((s) => s.name) })),
}));

const out = path.resolve(here, "../../backend/app/data/catalog.json");
const json = JSON.stringify(catalog, null, 2) + "\n";

if (process.argv.includes("--check")) {
  let current = "";
  try { current = readFileSync(out, "utf8"); } catch { /* missing = stale */ }
  if (current !== json) {
    console.error("catalog.json is stale. Run: node frontend/scripts/export-catalog.mjs");
    process.exit(1);
  }
  console.log("catalog.json is up to date");
} else {
  writeFileSync(out, json);
  console.log(`wrote ${catalog.length} courses to ${out}`);
}
