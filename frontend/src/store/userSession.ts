import { create } from "zustand";
import { persist } from "zustand/middleware";

interface UserHistory {
  PrevCourses?: { id: number }[];
  orders?: unknown[];
  address?: unknown[];
  [key: string]: unknown;
}

interface UserSessionState {
  currentuser: Record<string, unknown>;
  currentusercountry: string | null;
  currency: string;
  currentuserhistory: UserHistory;
  isLoading: boolean;
  isUserLoggedIn: boolean;
  TransactionId: string | null;
  isPreviewMode: boolean;
  signinInProgress: boolean;

  setCurrentUser: (user: Record<string, unknown>) => void;
  setCurrentuserCountry: (country: string) => void;
  setCurrentUserHistory: (history: UserHistory, type: string, loginStatus: boolean) => void;
  setTransactionId: (id: string | null) => void;
  setPreviewMode: (mode: boolean) => void;
  setSigsinInProgress: (val: boolean) => void;
  setIsLoading: (val: boolean) => void;
  isCourseBought: (courseId: number) => boolean;
  logout: () => void;
}

export const useUserSessionStore = create<UserSessionState>()(
  persist(
    (set, get) => ({
      currentuser: {},
      currentusercountry: null,
      currency: "$",
      currentuserhistory: {},
      isLoading: true,
      isUserLoggedIn: false,
      TransactionId: null,
      isPreviewMode: true,
      signinInProgress: false,

      setCurrentUser: (user) =>
        set({ currentuser: user, isUserLoggedIn: true }),

      setCurrentuserCountry: (country) =>
        set({
          currentusercountry: country,
          currency: country === "India" ? "₹" : "$",
        }),

      setCurrentUserHistory: (history, _type, loginStatus) =>
        set({ currentuserhistory: history, isUserLoggedIn: loginStatus }),

      setTransactionId: (id) => set({ TransactionId: id }),

      setPreviewMode: (mode) => set({ isPreviewMode: mode }),

      setSigsinInProgress: (val) => set({ signinInProgress: val }),

      setIsLoading: (val) => set({ isLoading: val }),

      isCourseBought: (courseId) => {
        const { currentuserhistory } = get();
        if (!currentuserhistory?.PrevCourses) return false;
        return currentuserhistory.PrevCourses.some((c) => c.id === courseId);
      },

      logout: () =>
        set({
          currentuser: {},
          currentuserhistory: {},
          isUserLoggedIn: false,
          isPreviewMode: true,
          TransactionId: null,
        }),
    }),
    {
      name: "user-session",
    }
  )
);
