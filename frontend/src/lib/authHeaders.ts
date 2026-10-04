import { auth } from "./firebase";

// The backend verifies this Firebase ID token and takes the student id from it.
// getIdToken() refreshes an expired token automatically.
export async function authHeaders(): Promise<Record<string, string>> {
  const token = await auth.currentUser?.getIdToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
