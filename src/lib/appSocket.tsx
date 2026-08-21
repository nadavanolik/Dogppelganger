/**
 * The single app-wide socket: `/api/ws`.
 *
 * One connection per signed-in client, opened once and reused for everything —
 * upload progress, incoming DMs, read receipts and bell notifications. It
 * replaces `uploadSocket.ts`, which was a second connection keyed by a
 * client-supplied owner string.
 *
 * Server -> client only. Nothing is sent up except a keep-alive: a DM is
 * persisted by `POST /api/dm/...` first and pushed second, so the socket going
 * down loses nothing — the message is already a row, and the inbox shows it
 * with an unread badge on the next load.
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

import { useAuth } from "./auth";
import { useMediaToken } from "./useMediaToken";

export type SocketEvent = { type: string; payload: Record<string, unknown> };
export type SocketStatus = "idle" | "connecting" | "open" | "closed";

type Handler = (event: SocketEvent) => void;

type AppSocketValue = {
  status: SocketStatus;
  /** Subscribe to one event type. Returns an unsubscribe function. */
  subscribe: (type: string, handler: Handler) => () => void;
};

// nginx closes an idle proxied connection after 60s, so keep it warm.
const PING_INTERVAL = 25_000;
const MAX_BACKOFF = 8_000;

const AppSocketContext = createContext<AppSocketValue | null>(null);

export function AppSocketProvider({ children }: { children: ReactNode }) {
  const { status: authStatus } = useAuth();
  const token = useMediaToken();
  const [status, setStatus] = useState<SocketStatus>("idle");
  const handlers = useRef(new Map<string, Set<Handler>>());

  const subscribe = useCallback((type: string, handler: Handler) => {
    const set = handlers.current.get(type) ?? new Set<Handler>();
    set.add(handler);
    handlers.current.set(type, set);
    return () => {
      set.delete(handler);
      if (set.size === 0) handlers.current.delete(type);
    };
  }, []);

  useEffect(() => {
    if (authStatus !== "authed" || !token) {
      setStatus("idle");
      return;
    }

    let cancelled = false;
    let attempt = 0;
    let socket: WebSocket | null = null;
    let reconnectTimer: number | undefined;
    let pingTimer: number | undefined;

    const connect = () => {
      if (cancelled) return;
      setStatus("connecting");
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      socket = new WebSocket(
        `${proto}//${window.location.host}/api/ws?token=${encodeURIComponent(token)}`,
      );

      socket.onopen = () => {
        if (cancelled) return;
        attempt = 0;
        setStatus("open");
        pingTimer = window.setInterval(() => {
          // A bare string, which the server special-cases. It used to parse
          // every frame as JSON and this closed the connection every 25s.
          if (socket?.readyState === WebSocket.OPEN) socket.send("ping");
        }, PING_INTERVAL);
      };

      socket.onmessage = (ev) => {
        if (cancelled) return;
        let message: SocketEvent;
        try {
          message = JSON.parse(ev.data as string);
        } catch {
          return;
        }
        for (const handler of handlers.current.get(message.type) ?? []) {
          handler(message);
        }
      };

      socket.onclose = () => {
        window.clearInterval(pingTimer);
        if (cancelled) return;
        setStatus("closed");
        attempt += 1;
        reconnectTimer = window.setTimeout(
          connect,
          Math.min(500 * 2 ** (attempt - 1), MAX_BACKOFF),
        );
      };
    };

    connect();

    return () => {
      cancelled = true;
      window.clearTimeout(reconnectTimer);
      window.clearInterval(pingTimer);
      socket?.close();
    };
  }, [authStatus, token]);

  const value = useMemo<AppSocketValue>(() => ({ status, subscribe }), [status, subscribe]);
  return <AppSocketContext.Provider value={value}>{children}</AppSocketContext.Provider>;
}

/** Run `handler` whenever an event of `type` arrives. */
export function useSocketEvent(type: string, handler: Handler) {
  const ctx = useContext(AppSocketContext);
  // Keep the latest handler without resubscribing on every render.
  const ref = useRef(handler);
  useEffect(() => {
    ref.current = handler;
  }, [handler]);

  useEffect(() => {
    if (!ctx) return;
    return ctx.subscribe(type, (event) => ref.current(event));
  }, [ctx, type]);
}

export function useSocketStatus(): SocketStatus {
  return useContext(AppSocketContext)?.status ?? "idle";
}
