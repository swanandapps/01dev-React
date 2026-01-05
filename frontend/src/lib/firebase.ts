import { initializeApp } from "firebase/app";
import { getAuth, GoogleAuthProvider, signInWithPopup, onAuthStateChanged, signOut } from "firebase/auth";
import { getFirestore, doc, getDoc, setDoc } from "firebase/firestore";
import { getStorage } from "firebase/storage";
import { initializeAppCheck, ReCaptchaEnterpriseProvider } from "firebase/app-check";

const firebaseConfig = {
  apiKey: "AIzaSyDAzBM9h5F7qDazxPSiLsPxLEIUpG9V_Ds",
  authDomain: "topdev-93530.firebaseapp.com",
  projectId: "topdev-93530",
  storageBucket: "topdev-93530.appspot.com",
  messagingSenderId: "772834319609",
  appId: "1:772834319609:web:98cf66d19b72bdb2ae1628",
  measurementId: "G-GJ8ZXV3JTN",
};

export const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);
export const db = getFirestore(app);
export const storage = getStorage(app);
export const googleProvider = new GoogleAuthProvider();

if (typeof window !== "undefined") {
  try {
    initializeAppCheck(app, {
      provider: new ReCaptchaEnterpriseProvider("6LcFKG0pAAAAAG3OVGxC4WZYoh_mQwP-x8jSeznf"),
      isTokenAutoRefreshEnabled: true,
    });
  } catch {
    // App check may already be initialized
  }
}

export async function FBisNewUser(uid: string): Promise<boolean> {
  const ref = doc(db, "users", uid);
  const snap = await getDoc(ref);
  return !snap.exists();
}

export async function FBNewSignup(user: { uid: string; displayName: string | null; email: string | null; photoURL: string | null }) {
  const ref = doc(db, "users", user.uid);
  await setDoc(ref, {
    uid: user.uid,
    name: user.displayName,
    email: user.email,
    photo: user.photoURL,
    PrevCourses: [],
    orders: [],
    address: [],
    createdAt: new Date().toISOString(),
  });
}

export async function FBgetLoggedUserandStoreHistory(uid: string) {
  const ref = doc(db, "users", uid);
  const snap = await getDoc(ref);
  if (snap.exists()) {
    return snap.data();
  }
  return null;
}

export async function FBgetChatHistory(uid: string): Promise<unknown[]> {
  const ref = doc(db, "chatHistories", uid);
  const snap = await getDoc(ref);
  if (snap.exists()) {
    const data = snap.data();
    return Array.isArray(data.messages) ? data.messages : [];
  }
  return [];
}

export async function FBsaveChatHistory(uid: string, messages: unknown[]) {
  const ref = doc(db, "chatHistories", uid);
  // Cap to the last 60 turns so the doc stays well under Firestore's 1MB limit.
  await setDoc(ref, { messages: messages.slice(-60), updatedAt: new Date().toISOString() });
}

export { onAuthStateChanged, signInWithPopup, signOut };
