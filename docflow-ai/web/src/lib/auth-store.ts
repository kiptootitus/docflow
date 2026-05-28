import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { User } from "@/lib/api";
import { authApi } from "@/lib/api";

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;

  // Core auth actions
  login: (
    email: string,
    password: string
  ) => Promise<{ two_factor_required?: boolean; email?: string }>;
  handleLoginSuccess: (tokens: { access: string; refresh: string }) => Promise<void>;
  logout: () => Promise<void>;
  fetchMe: () => Promise<void>;
  setTokens: (access: string, refresh: string) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      // ── Initial state ──────────────────────────────────────────────────
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: false,

      // ── setTokens ──────────────────────────────────────────────────────
      // Persists tokens in both localStorage (for the axios interceptor) and
      // Zustand state (for reactive UI).
      setTokens: (access, refresh) => {
        localStorage.setItem("access_token", access);
        localStorage.setItem("refresh_token", refresh);
        set({
          accessToken: access,
          refreshToken: refresh,
          isAuthenticated: true,
        });
      },

      // ── login ──────────────────────────────────────────────────────────
      // Returns { two_factor_required, email } so the UI can branch into a
      // TOTP challenge without navigating away.
      login: async (email, password) => {
        set({ isLoading: true });
        try {
          const { data } = await authApi.login(email, password);

          // Happy path – no 2FA
          if (!data.two_factor_required && data.access && data.refresh) {
            await get().handleLoginSuccess({
              access: data.access,
              refresh: data.refresh,
            });
          }

          return {
            two_factor_required: data.two_factor_required ?? false,
            email: data.email,
          };
        } finally {
          set({ isLoading: false });
        }
      },

      // ── handleLoginSuccess ─────────────────────────────────────────────
      // Called after a successful login OR after a successful TOTP verify.
      handleLoginSuccess: async (tokens) => {
        get().setTokens(tokens.access, tokens.refresh);
        await get().fetchMe();
      },

      // ── logout ─────────────────────────────────────────────────────────
      // Clears every trace of the session.  Server-side token invalidation is
      // best-effort – a network failure must not block the local logout.
      logout: async () => {
        const refresh =
          get().refreshToken || localStorage.getItem("refresh_token");

        // Best-effort: tell the backend to blacklist the refresh token
        if (refresh) {
          try {
            await authApi.logout(refresh);
          } catch {
            // Silently ignore – the local session is cleared regardless
          }
        }

        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
        });
      },

      // ── fetchMe ────────────────────────────────────────────────────────
      // Loads the current user profile.  On any auth failure, forces a full
      // logout so the app never sits in a half-authenticated state.
      fetchMe: async () => {
        try {
          const { data } = await authApi.me();
          set({ user: data });
        } catch (err) {
          // Token is invalid / expired beyond refresh – clear everything
          await get().logout();
          throw err;
        }
      },
    }),

    // ── Persistence config ───────────────────────────────────────────────
    // Only persist the tokens and the auth flag.  The `user` object is
    // re-fetched on every page load via fetchMe so it stays fresh.
    {
      name: "docflow-auth",
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);