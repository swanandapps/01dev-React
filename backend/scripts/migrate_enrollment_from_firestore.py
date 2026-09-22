"""
One-off migration: copies existing Firestore users/{uid}.PrevCourses into the
new Postgres `enrollments` collection (enrollment_service). After this runs
and the frontend/backend deploy that stop reading/writing Firestore for
enrollment, Firestore's PrevCourses field is dead data — kept as-is (not
deleted) since Firebase remains the auth/profile record for other fields
(name, email, photo, orders, address), just not for enrollment anymore.

Reads Firestore via the REST API using the operator's own gcloud access
token (`gcloud auth print-access-token`) — this script is run locally by a
human with real gcloud access, not by any deployed service.

Field-shape note (found by inspecting the real data before writing this):
existing entries use "name" for the course title, not "title" (which is
what the current frontend write path actually uses going forward) — and
5 of 7 real entries have no "purchasedAt" at all (written before that field
existed). Handles both; falls back to the Firestore document's own
createTime when purchasedAt is missing, since a migration import shouldn't
fabricate a specific purchase date it doesn't have.

Also drops course id 0 — not a real track id (catalog starts at 1); found
as stray/duplicate legacy data on one account.

Run: backend/.venv/bin/python scripts/migrate_enrollment_from_firestore.py
"""
import asyncio
import subprocess

import httpx
from dotenv import load_dotenv
load_dotenv()

from app.services import enrollment_service  # noqa: E402

PROJECT_ID = "topdev-93530"
FIRESTORE_URL = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents:runQuery"


def _gcloud_token() -> str:
    return subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()


async def main():
    token = _gcloud_token()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            FIRESTORE_URL,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"structuredQuery": {"from": [{"collectionId": "users"}]}},
        )
        resp.raise_for_status()
        rows = resp.json()

    migrated_accounts = 0
    migrated_courses = 0
    for row in rows:
        doc = row.get("document")
        if not doc:
            continue
        uid = doc["name"].split("/")[-1]
        fields = doc.get("fields", {})
        prev_courses = fields.get("PrevCourses", {}).get("arrayValue", {}).get("values", [])
        if not prev_courses:
            continue
        doc_create_time = doc.get("createTime")

        touched = False
        for entry in prev_courses:
            f = entry.get("mapValue", {}).get("fields", {})
            course_id = int(f.get("id", {}).get("integerValue", -1))
            if course_id <= 0:
                continue  # stray legacy data — not a real track id
            title = f.get("name", {}).get("stringValue") or f.get("title", {}).get("stringValue")
            if not title:
                continue
            purchased_at = f.get("purchasedAt", {}).get("stringValue") or doc_create_time
            await enrollment_service.enroll(uid, course_id, title, purchased_at=purchased_at)
            migrated_courses += 1
            touched = True
        if touched:
            migrated_accounts += 1
            print(f"  migrated {uid}: {[e.get('mapValue',{}).get('fields',{}).get('name',{}).get('stringValue') for e in prev_courses]}")

    print(f"\nDone — {migrated_accounts} accounts, {migrated_courses} course enrollments migrated to Postgres.")


if __name__ == "__main__":
    asyncio.run(main())
