import { auth } from "./firebase";

// The backend verifies this Firebase ID token and takes the student id from it.
// On a page reload auth.currentUser is null until Firebase restores the session,
// while the persisted session store already says "signed in" — so wait for the
// initial auth state first (instant after that). getIdToken() refreshes an
// expired token automatically.
export async function authHeaders(): Promise<Record<string, string>> {
  await auth.authStateReady();
  const token = await auth.currentUser?.getIdToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
