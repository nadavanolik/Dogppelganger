/**
 * The real session: a JWT from `/api/auth`, held in localStorage.
 *
 * This replaces the mock in `store.tsx`, where "logging in" meant finding a
 * hardcoded account by email and ignoring the password entirely.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { ApiError, api, setAuthToken, setMediaToken, setUnauthorizedHandler } from "./api";

export type User = { id: number; username: string; email: string };

type TokenResponse = {
  access_token: string;
  media_token: string;
  user: User;
};

/**
 * `loading` is not decoration — it is the difference between working and
 * broken. On a hard refresh the token is in localStorage but the user has not
 * been fetched yet; without a distinct third state every route guard would see
 * `user === null` on the first frame and bounce a signed-in person to /login.
 */
export type AuthStatus = "loading" | "authed" | "anon";

type AuthContextValue = {
  status: AuthStatus;
  user: User | null;
  login: (email: string, password: string) => Promise<User>;
  signup: (email: string, username: string, password: string) => Promise<User>;
  logout: () => void;
  refresh: () => Promise<void>;
  /** After a password change the server issues a new pair; adopt them. */
  adoptTokens: (tokens: TokenResponse) => void;
};

const TOKEN_KEY = "dogppelganger_token";

const AuthContext = createContext<AuthContextValue | null>(null);

function readStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<User | null>(null);
  // The media token is short-lived, so it is re-minted rather than persisted.
  const mediaTimer = useRef<number | null>(null);

  const clear = useCallback(() => {
    try {
      localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* private browsing — nothing to clean up */
    }
    setAuthToken(null);
    setMediaToken(null);
    setUser(null);
    setStatus("anon");
    if (mediaTimer.current) window.clearInterval(mediaTimer.current);
    mediaTimer.current = null;
  }, []);

  const startMediaRefresh = useCallback(() => {
    if (mediaTimer.current) window.clearInterval(mediaTimer.current);
    // The server issues these with a 15-minute life; re-mint well inside that
    // so an <img> never renders against an expired one.
    mediaTimer.current = window.setInterval(
      async () => {
        try {
          const res = await api.get<{ media_token: string }>("/api/auth/media-token");
          setMediaToken(res.media_token);
        } catch {
          /* a 401 already triggered logout; anything else retries next tick */
        }
      },
      10 * 60 * 1000,
    );
  }, []);

  const adoptTokens = useCallback(
    (tokens: TokenResponse) => {
      try {
        localStorage.setItem(TOKEN_KEY, tokens.access_token);
      } catch {
        /* private browsing: the session still works for this tab */
      }
      setAuthToken(tokens.access_token);
      setMediaToken(tokens.media_token);
      setUser(tokens.user);
      setStatus("authed");
      startMediaRefresh();
    },
    [startMediaRefresh],
  );

  const refresh = useCallback(async () => {
    const me = await api.get<User>("/api/auth/me");
    setUser(me);
  }, []);

  // Bootstrap: adopt a stored token, then prove it still works. The user object
  // is deliberately not persisted, so a renamed — or deleted — account can't
  // linger in a stale tab.
  useEffect(() => {
    const token = readStoredToken();
    if (!token) {
      setStatus("anon");
      return;
    }
    setAuthToken(token);
    let cancelled = false;
    (async () => {
      try {
        const [me, media] = await Promise.all([
          api.get<User>("/api/auth/me"),
          api.get<{ media_token: string }>("/api/auth/media-token"),
        ]);
        if (cancelled) return;
        setMediaToken(media.media_token);
        setUser(me);
        setStatus("authed");
        startMediaRefresh();
      } catch {
        if (!cancelled) clear();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [clear, startMediaRefresh]);

  // Any 401 from anywhere ends the session exactly once.
  useEffect(() => {
    setUnauthorizedHandler(clear);
    return () => setUnauthorizedHandler(() => {});
  }, [clear]);

  useEffect(() => {
    return () => {
      if (mediaTimer.current) window.clearInterval(mediaTimer.current);
    };
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const tokens = await api.post<TokenResponse>("/api/auth/login", { email, password });
      adoptTokens(tokens);
      return tokens.user;
    },
    [adoptTokens],
  );

  const signup = useCallback(
    async (email: string, username: string, password: string) => {
      const tokens = await api.post<TokenResponse>("/api/auth/signup", {
        email,
        username,
        password,
      });
      adoptTokens(tokens);
      return tokens.user;
    },
    [adoptTokens],
  );

  const value = useMemo<AuthContextValue>(
    () => ({ status, user, login, signup, logout: clear, refresh, adoptTokens }),
    [status, user, login, signup, clear, refresh, adoptTokens],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

/** The signed-in user, or null. */
export function useCurrentUser(): User | null {
  return useAuth().user;
}

export { ApiError };
