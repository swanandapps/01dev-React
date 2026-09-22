# Lab Phase 4 — Lecture as a Source, and the In-Course Entry Point — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a student generate flashcards, a summary, a study plan or a quiz **from a course lecture they're already watching**, with no upload — the transcripts are already indexed on the backend.

**Architecture:** A third ingest source alongside typed text and PDF. The backend already has `vector_store.get_lecture_transcript(lecture_id)`, so this is one endpoint plus a picker: the UI asks the backend which lectures have transcripts and posts back a `lecture_id`, rather than shipping a transcript to the browser and back.

**Tech Stack:** FastAPI, React + Vite, the existing in-memory `vector_store`.

**Spec:** `docs/superpowers/specs/2026-09-22-lab-content-pipeline-design.md`

**Depends on:** Phases 1–3 complete (`/api/lab/*` live, `LabStudio` exists).

## Global Constraints

- **The UI must not map `tracks.ts` chapters to backend lecture ids.** The frontend's static course structure and the backend's transcript `lecture_id`s (e.g. `react-perf-4-1`) have no reliable correspondence. The backend is the source of truth for which lectures have transcripts; the UI lists what it reports.
- **A lecture-sourced concept is course-grounded.** Pass the lecture's `course_id` through so `concept_resolver.resolve(candidate, course_id=...)` attaches any newly-discovered concept to that course rather than to nothing. This is the one functional difference from an uploaded PDF, and it is the reason `source_ref` exists.
- **Keep the existing upload endpoints.** This adds a third source; it does not restructure `/upload-text` or `/upload`. The spec sketched a single `/ingest` with a `source` field, but Phases 1–3 built on the two existing endpoints to preserve the Mastra parity contract — adding a third in the same style is lower risk than churning a working contract.
- `LabStudio`'s `lectureText` prop from Phase 3 was a placeholder that nothing passed. **Replace it with `courseId`** — the studio fetches the lecture list itself.
- Tests: `bash backend/scripts/run_tests.sh`. Deploys: backend `railway up --service the01dev-backend`, frontend `npm run build && netlify deploy --prod --dir=dist`. No Hermes redeploy.

---

## File Structure

**Modified:**
- `app/services/lab/routes.py` — `GET /lectures`, `POST /upload-lecture`
- `frontend/src/lib/labApi.ts` — `getLectures`, `uploadLecture`
- `frontend/src/components/lab/LabStudio.tsx` — a third source mode with a lecture picker; `lectureText` prop → `courseId`
- `frontend/src/components/learn/CourseCompanion.tsx` — pass the course id through
- `frontend/src/pages/CoursePlayerPage.tsx` — pass the course id to the companion

**Created:**
- `backend/tests/test_lab_lecture_source.py`

---

### Task 1: Lecture listing and ingestion

**Files:**
- Modify: `backend/app/services/lab/routes.py`
- Test: `backend/tests/test_lab_lecture_source.py`

**Interfaces:**
- Consumes: `vector_store.get_course_lectures(course_id)`, `vector_store.get_lecture_transcript(lecture_id)`, `vector_store.get_lecture_meta(lecture_id)`
- Produces:
  - `GET /api/lab/lectures?course_id=` → `[{lecture_id, lecture_title}]`
  - `POST /api/lab/upload-lecture {lecture_id}` → `{docId, title, course_id}`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_lab_lecture_source.py`:

```python
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(monkeypatch):
    from app.services.lab import routes as lab_routes

    class FakeVectorStore:
        def get_course_lectures(self, course_id):
            if course_id != "react-perf":
                return []
            return [
                {"lecture_id": "react-perf-3-2", "lecture_title": "3.2 - Memoization"},
                {"lecture_id": "react-perf-4-1", "lecture_title": "4.1 - React.memo"},
            ]

        def get_lecture_transcript(self, lecture_id):
            return "React.memo skips a re-render when props are shallowly equal." \
                if lecture_id == "react-perf-4-1" else ""

        def get_lecture_meta(self, lecture_id):
            if lecture_id != "react-perf-4-1":
                return None
            return {"lecture_id": lecture_id, "lecture_title": "4.1 - React.memo",
                    "course_id": "react-perf", "course_title": "React Performance Patterns"}

    monkeypatch.setattr(lab_routes, "vector_store", FakeVectorStore())
    return TestClient(app)


def test_lists_lectures_for_a_course(client):
    r = client.get("/api/lab/lectures?course_id=react-perf")
    assert r.status_code == 200
    assert [l["lecture_id"] for l in r.json()] == ["react-perf-3-2", "react-perf-4-1"]


def test_lists_nothing_for_a_course_without_transcripts(client):
    assert client.get("/api/lab/lectures?course_id=nope").json() == []


def test_upload_lecture_creates_a_doc_from_the_transcript(client):
    r = client.post("/api/lab/upload-lecture", json={"lecture_id": "react-perf-4-1"})
    assert r.status_code == 200
    body = r.json()
    assert body["docId"]
    assert body["title"] == "4.1 - React.memo"
    # course_id is what makes a lecture-sourced concept course-grounded
    assert body["course_id"] == "react-perf"


def test_uploaded_lecture_drives_generation(client):
    doc = client.post("/api/lab/upload-lecture",
                      json={"lecture_id": "react-perf-4-1"}).json()["docId"]
    from app.services.lab import routes as lab_routes
    assert lab_routes.DOCS[doc]["text"].startswith("React.memo skips")
    assert lab_routes.DOCS[doc]["course_id"] == "react-perf"


def test_unknown_lecture_is_404(client):
    r = client.post("/api/lab/upload-lecture", json={"lecture_id": "does-not-exist"})
    assert r.status_code == 404


def test_lecture_with_no_extractable_transcript_is_400(client, monkeypatch):
    from app.services.lab import routes as lab_routes

    class Empty:
        def get_lecture_meta(self, lecture_id):
            return {"lecture_id": lecture_id, "lecture_title": "T", "course_id": "c"}

        def get_lecture_transcript(self, lecture_id):
            return "   "

        def get_course_lectures(self, course_id):
            return []

    monkeypatch.setattr(lab_routes, "vector_store", Empty())
    r = client.post("/api/lab/upload-lecture", json={"lecture_id": "x"})
    assert r.status_code == 400
```

- [ ] **Step 2: Run them to verify they fail**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/backend
.venv/bin/python -m pytest tests/test_lab_lecture_source.py -v
```

Expected: FAIL — both routes 404, and `lab_routes` has no `vector_store` attribute to patch.

- [ ] **Step 3: Add the endpoints**

In `backend/app/services/lab/routes.py`, add the import:

```python
from app.services.vector_store import vector_store
```

Add the request model next to the others:

```python
class UploadLectureReq(BaseModel):
    lecture_id: str
```

Add the endpoints after `upload_pdf`:

```python
@router.get("/lectures")
async def list_course_lectures(course_id: str):
    """Which lectures of this course have transcripts the Lab can use.

    The backend is the source of truth here: the frontend's static course
    structure (tracks.ts chapters) has no reliable correspondence to transcript
    lecture ids, so the UI lists what this returns rather than guessing.
    """
    return vector_store.get_course_lectures(course_id)


@router.post("/upload-lecture")
async def upload_lecture(req: UploadLectureReq):
    """Use an indexed course lecture as the material — no upload needed.

    Records `course_id` on the doc: a concept discovered in a real course
    lecture is course-grounded, so the resolver attaches any new node to that
    course instead of to nothing. That is the one functional difference between
    this source and an uploaded PDF.
    """
    meta = vector_store.get_lecture_meta(req.lecture_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Unknown lecture")
    text = (vector_store.get_lecture_transcript(req.lecture_id) or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="lecture has no transcript text")
    doc_id = uuid.uuid4().hex[:12]
    title = meta.get("lecture_title") or req.lecture_id
    DOCS[doc_id] = {
        "text": text,
        "title": title,
        "course_id": meta.get("course_id"),
        "source": "lecture",
        "source_ref": req.lecture_id,
    }
    return {"docId": doc_id, "title": title, "course_id": meta.get("course_id")}
```

- [ ] **Step 4: Pass the course through to the resolver**

A lecture-sourced quiz must resolve concepts against that course. In `generate_outputs`, pass it into the lesson graph state:

```python
    lesson_values = await run_in_threadpool(
        GRAPH.invoke,
        {"doc": doc["text"], "title": doc["title"], "results": [],
         "doc_id": req.docId, "course_id": doc.get("course_id")},
        _cfg(lesson_id),
    )
```

Add `course_id: str` to `LessonState` in `app/services/lab/graph.py`, and pass it to the generator in the `generate_quiz` node:

```python
    questions = gen_quiz(state["doc"], obj, state.get("questions_per_quiz", 3),
                         course_id=state.get("course_id"))
```

In `app/services/lab/llm.py`, accept and forward it:

```python
def gen_quiz(document: str, objective: dict, n: int, course_id: str | None = None) -> list[dict]:
```

and in the resolution loop added in Phase 2:

```python
        q["concept"] = asyncio.run(resolve_concept(candidate, course_id)) if candidate else ""
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_lab_lecture_source.py -v
bash scripts/run_tests.sh
```

Expected: 6 passed, then `ALL PASSED`. Phase 2's `test_lab_quiz_concepts.py` still passes because `course_id` defaults to `None`.

- [ ] **Step 6: Commit**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes
git add backend/app/services/lab/ backend/tests/test_lab_lecture_source.py
git commit -m "feat: use an indexed course lecture as Lab material

GET /lectures lists what actually has transcripts (the backend is the source
of truth — tracks.ts chapters don't map to transcript lecture ids), and
/upload-lecture turns one into a doc with no upload.

Carries course_id through to the resolver, so a concept first discovered in
a real lecture attaches to that course rather than to nothing — the one
functional difference between this source and an uploaded PDF."
```

---

### Task 2: The lecture picker in the studio

**Files:**
- Modify: `frontend/src/lib/labApi.ts`
- Modify: `frontend/src/components/lab/LabStudio.tsx`

**Interfaces:**
- Produces:
  - `getLectures(courseId: string): Promise<Lecture[]>` where `Lecture = {lecture_id, lecture_title}`
  - `uploadLecture(lectureId: string): Promise<{docId: string; title: string; course_id: string}>`
  - `<LabStudio studentId courseId?={string} onClose />` — replaces Phase 3's unused `lectureText` prop

- [ ] **Step 1: Add the client calls**

Append to `frontend/src/lib/labApi.ts`:

```typescript
export type Lecture = { lecture_id: string; lecture_title: string };

export async function getLectures(courseId: string): Promise<Lecture[]> {
  const res = await fetch(`${BASE}/lectures?course_id=${encodeURIComponent(courseId)}`);
  if (!res.ok) throw new Error(`Lab API error ${res.status}`);
  return res.json();
}

export function uploadLecture(
  lectureId: string,
): Promise<{ docId: string; title: string; course_id: string }> {
  return post("/upload-lecture", { lecture_id: lectureId });
}
```

- [ ] **Step 2: Add the third source mode**

In `frontend/src/components/lab/LabStudio.tsx`:

Replace the props type and destructuring — swap `lectureText?: string` for `courseId?: string`:

```tsx
export function LabStudio({
  studentId,
  onClose,
  courseId,
}: {
  studentId: string;
  onClose: () => void;
  courseId?: string;
}) {
```

Extend the mode type and add lecture state:

```tsx
type InputMode = "text" | "pdf" | "lecture";
```

```tsx
  const [lectures, setLectures] = useState<Lecture[]>([]);
  const [lectureId, setLectureId] = useState("");
```

Import what's needed: `useEffect` from react, and `getLectures, uploadLecture` plus `type Lecture` from `../../lib/labApi`.

Default to the lecture tab when opened in a course, and fetch the list:

```tsx
  const [mode, setMode] = useState<InputMode>(courseId ? "lecture" : "text");

  useEffect(() => {
    if (!courseId) return;
    getLectures(courseId)
      .then((ls) => {
        setLectures(ls);
        if (ls.length) setLectureId(ls[0].lecture_id);
      })
      .catch(() => setLectures([]));
  }, [courseId]);
```

Update the tab list so the lecture tab only appears in a course:

```tsx
            {(["text", "pdf", ...(courseId ? (["lecture"] as const) : [])] as InputMode[]).map((m) => (
```

with labels:

```tsx
                  {m === "pdf" ? <Upload className="w-3.5 h-3.5" />
                    : m === "lecture" ? <Video className="w-3.5 h-3.5" />
                    : <NotebookPen className="w-3.5 h-3.5" />}
                  {m === "pdf" ? "Upload PDF" : m === "lecture" ? "This course" : "Type notes / topic"}
```

Import `Video` from lucide-react.

Add the picker, rendered when `mode === "lecture"` (alongside the existing `mode === "text"` / `pdf` branches):

```tsx
          {mode === "lecture" && (
            <div className="flex flex-col gap-2">
              <label className="text-xs font-medium text-zinc-500 uppercase tracking-wide">
                Pick a lecture
              </label>
              {lectures.length === 0 ? (
                <p className="text-sm text-zinc-500 bg-zinc-800/40 border border-zinc-700/50 rounded-xl px-4 py-3">
                  No transcripts are available for this course yet — paste notes or upload a PDF instead.
                </p>
              ) : (
                <select
                  value={lectureId}
                  onChange={(e) => setLectureId(e.target.value)}
                  className="w-full bg-zinc-800/60 border border-zinc-700/60 rounded-xl px-4 py-3 text-sm text-zinc-100 outline-none focus:border-indigo-500/60"
                >
                  {lectures.map((l) => (
                    <option key={l.lecture_id} value={l.lecture_id}>{l.lecture_title}</option>
                  ))}
                </select>
              )}
              <p className="text-xs text-zinc-600">
                Uses the lecture's transcript — nothing to upload.
              </p>
            </div>
          )}
```

Update `canSubmit`:

```tsx
  const canSubmit =
    selected.length > 0 &&
    (mode === "pdf" ? !!pdfFile
      : mode === "lecture" ? !!lectureId
      : !!(notes.trim() || topic.trim()));
```

Update `handleGenerate`'s ingestion branch:

```tsx
      let docId: string;
      if (mode === "pdf") {
        if (!pdfFile) throw new Error("Please choose a PDF file.");
        docId = (await quizApi.uploadPdf(pdfFile)).docId;
      } else if (mode === "lecture") {
        if (!lectureId) throw new Error("Please pick a lecture.");
        docId = (await uploadLecture(lectureId)).docId;
      } else {
        const text = notes.trim() || topic.trim();
        if (!text) throw new Error("Please enter some notes or a topic.");
        docId = (await quizApi.uploadText(text, topic.trim() || undefined)).docId;
      }
```

Finally remove the `lectureText` banner and the `setNotes(lectureText ?? "")` calls in `restart()` and the initial `notes` state — replace both with `""`.

- [ ] **Step 3: Build**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/frontend && npm run build
```

Expected: clean. Fix type errors before moving on.

- [ ] **Step 4: Commit**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes
git add frontend/src/lib/labApi.ts frontend/src/components/lab/LabStudio.tsx
git commit -m "feat: lecture picker as a third Lab source

Replaces Phase 3's unused lectureText placeholder with courseId: the studio
asks the backend which lectures have transcripts and posts back an id,
rather than shipping a transcript to the browser and back. Defaults to the
lecture tab when opened inside a course."
```

---

### Task 3: Wire the in-course entry point

**Files:**
- Modify: `frontend/src/components/learn/CourseCompanion.tsx`
- Modify: `frontend/src/pages/CoursePlayerPage.tsx`

**Interfaces:**
- Consumes: `<LabStudio courseId=... />`
- Produces: the companion's notes tool opens the studio with the course's lectures pre-listed

- [ ] **Step 1: Pass the course id through the companion**

In `frontend/src/components/learn/CourseCompanion.tsx`, the component already receives `course: Course`, which carries `course_id`. Pass it to the studio added in Phase 3:

```tsx
            <LabStudio studentId={userId} courseId={course.course_id}
                       onClose={() => setTool(null)} />
```

- [ ] **Step 2: Make sure the player's tutor panel offers it**

`CoursePlayerPage.tsx` renders `<PlayerTutor course={aiCourse} userId={userId} lectureTitle={...} />`. Confirm whether `PlayerTutor` exposes the companion's tool set; if it does not, add a Lab entry point to the player instead:

```tsx
      {aiCourse && (
        <CourseCompanion course={aiCourse} userId={userId} />
      )}
```

Read `frontend/src/components/learn/PlayerTutor.tsx` first and follow whichever pattern is already there — do not add a second competing entry point if one exists.

- [ ] **Step 3: Build and verify in a browser**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/frontend && npm run build && netlify deploy --prod --dir=dist
```

Open a course page on `the01.dev`, open the companion's notes/Lab tool, and confirm:
1. The **"This course"** tab is selected by default and lists that course's lectures.
2. Picking a lecture and ticking **flashcards** produces cards drawn from the lecture's actual content.
3. Ticking **quiz** produces questions about the lecture, not about something else.
4. On the standalone `/lab` page (no course), the "This course" tab does **not** appear.

- [ ] **Step 4: Commit**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes
git add frontend/src/components/learn/CourseCompanion.tsx frontend/src/pages/CoursePlayerPage.tsx
git commit -m "feat: open Lab from inside a course with that course's lectures listed"
```

---

### Task 4: Deploy and verify end to end

- [ ] **Step 1: Deploy the backend**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/backend
RAILWAY_CALLER="skill:use-railway@1.4.0" RAILWAY_AGENT_SESSION="lab-phase4" \
  railway up --service the01dev-backend --detach -m "feat: lecture as a Lab source"
```

Wait for SUCCESS.

- [ ] **Step 2: Verify against production**

```bash
BASE=https://the01dev-backend-production.up.railway.app/api/lab
SID=x94FcfXU7KRrobyOA4UHDukbRoC2

echo "=== lectures with transcripts ==="
curl -s "$BASE/lectures?course_id=react-perf" | python3 -m json.tool

echo "=== ingest one and make flashcards from it ==="
D=$(curl -s -X POST $BASE/upload-lecture -H "Content-Type: application/json" \
    -d '{"lecture_id":"react-perf-4-1"}' \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['docId'], d['title'], d['course_id'])")
echo "doc: $D"
DOC=$(echo $D | cut -d' ' -f1)
curl -s -X POST $BASE/generate -H "Content-Type: application/json" \
  -d "{\"docId\":\"$DOC\",\"outputs\":[\"flashcards\"],\"student_id\":\"$SID\"}" \
  | python3 -c "
import sys,json; b=json.load(sys.stdin)
cards=(b.get('artifacts') or {}).get('flashcards') or []
print('cards:', len(cards))
for c in cards[:3]: print(' -', c['front'], '->', c['back'][:60])
"
```

Expected: the lecture list shows `react-perf-3-2` and `react-perf-4-1`; the generated cards are clearly about React.memo/useCallback — i.e. drawn from that lecture's real transcript, not generic.

- [ ] **Step 3: Confirm a lecture-sourced concept attached to the course**

```bash
cd /Users/swanandkadam/Desktop/01dev-React-hermes/backend
PYTHONPATH=. .venv/bin/python -c "
import asyncio
from dotenv import load_dotenv; load_dotenv()
async def main():
    from app.services.store import store
    for c in await store.list_all('concepts'):
        if c.get('created_by') == 'student_content':
            print(f\"{c['name']:30} course_id={c.get('course_id')!r}\")
asyncio.run(main())
"
```

Expected: concepts first discovered from a **lecture** carry that lecture's `course_id`; concepts from uploaded PDFs carry `None`. If a lecture-discovered concept shows `None`, the `course_id` is not being threaded through Task 1 Step 4 correctly.

- [ ] **Step 4: Browser walkthrough**

Repeat Task 3 Step 3's checks on the deployed site, then confirm the artifacts landed in the library:

```bash
curl -s "$BASE/library?student_id=$SID" | python3 -c "
import sys,json
for r in json.load(sys.stdin)[:5]:
    print(r['artifact_type'], '|', r['doc_title'], '|', r['created_at'][:19])
"
```

Expected: an entry whose `doc_title` is the lecture's title (e.g. `4.1 - React.memo and useCallback`), proving the lecture-sourced run persisted like any other.

- [ ] **Step 5: Report design iteration needs**

As with Phase 3: note anything that wants the human partner's eye rather than treating it as finished — in particular whether defaulting to the "This course" tab inside a course is the right call, or whether students would expect their own notes first.

---

## Not in this plan (deliberately)

- **Multi-lecture or whole-course material** — one lecture at a time. `vector_store.get_course_transcript(course_id)` exists if whole-course material is wanted later.
- **Auto-selecting the lecture currently playing** — the picker defaults to the course's first lecture. Wiring it to the active video position needs a `tracks.ts`-to-`lecture_id` mapping, which this plan deliberately avoids.
- **Library management (rename/delete/re-generate)** — still read-only.
- **Prerequisite edges for newly created concepts** — nodes start isolated; inferring edges is its own piece of work.
