// Run: cd frontend && node --experimental-strip-types scripts/lectureMatch.check.ts
import assert from "node:assert/strict";
import tracks from "../src/data/tracks.ts";
import { findLecture, formatTimestamp, normaliseLectureTitle, resolveJump } from "../src/lib/lectureMatch.ts";

const chapters = [
  { name: "Chapter 8", subchapters: [
    { name: "8.1 - The `npm link` command", src: "" },
    { name: "8.2 - Testing Our NPM Package", src: "" },
  ] },
  { name: "Chapter 11", subchapters: [{ name: "11.1 - Publishing using `np`", src: "" }] },
];

assert.equal(normaliseLectureTitle("  11.1 -  Publishing using `np` "), "11.1 - publishing using np");
assert.deepEqual(findLecture(chapters, "11.1 - Publishing using `np`"), { chapter: 1, sub: 0 });
assert.deepEqual(findLecture(chapters, "11.1 - Publishing using np"), { chapter: 1, sub: 0 });
assert.deepEqual(findLecture(chapters, "8.1 - the NPM LINK   command"), { chapter: 0, sub: 0 });
assert.deepEqual(findLecture(chapters, "8.2 - Testing Our NPM Package"), { chapter: 0, sub: 1 });
assert.equal(findLecture(chapters, "9.9 - Not a lecture"), null);
assert.equal(findLecture(chapters, ""), null);
assert.equal(findLecture(chapters, "   "), null);
assert.equal(findLecture(chapters, "11.1"), null); // never a prefix match
const nothingLocked = () => false;
assert.deepEqual(resolveJump(chapters, "11.1 - Publishing using np", nothingLocked), { chapter: 1, sub: 0 });
assert.equal(resolveJump(chapters, "11.1 - Publishing using np", (c) => c >= 1), null); // locked chapter
assert.equal(resolveJump(chapters, "9.9 - Not a lecture", nothingLocked), null);
assert.equal(formatTimestamp(200), "03:20");
assert.equal(formatTimestamp(0), "00:00");
assert.equal(formatTimestamp(59.9), "00:59");
assert.equal(formatTimestamp(3725), "62:05");

// Every real lecture of Build a Custom Library (course id 2) resolves to its own position.
const course = tracks.find((t) => t.id === 2);
assert.ok(course, "course 2 missing from tracks.ts");
course.courseContent.forEach((ch, c) =>
  ch.subchapters.forEach((sub, s) => assert.deepEqual(findLecture(course.courseContent, sub.name), { chapter: c, sub: s })));
assert.deepEqual(findLecture(course.courseContent, "11.1 - Publishing using `np`"), { chapter: 10, sub: 0 });

console.log("lectureMatch: all checks passed");
