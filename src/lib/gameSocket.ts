/**
 * The multiplayer room socket.
 *
 * One connection per room page. The server is the authority on everything — we
 * send intents (`game_answer`, `game_start`) and render whatever state comes
 * back, never advancing the game locally.
 *
 * Events are named `game_*` on the wire so that when the backend folds this into
 * the shared `/api/ws` socket, the routing there is a prefix test and nothing in
 * the frontend has to change.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type { RoomState } from "./gameApi";

export type ServerEvent = { type: string; payload: Record<string, unknown> };

export type SocketStatus = "connecting" | "open" | "closed";

// nginx closes an idle proxied connection after 60s, so keep it warm.
const PING_INTERVAL = 25_000;
const MAX_BACKOFF = 8_000;

function socketUrl(playerId: string, playerName: string): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const params = new URLSearchParams({ playerId, name: playerName });
  return `${proto}//${window.location.host}/api/game/ws?${params}`;
}

export function useGameRoom(opts: {
  playerId: string | null;
  playerName: string;
  roomId?: string;
  code?: string;
  enabled?: boolean;
}) {
  const { playerId, playerName, roomId, code, enabled = true } = opts;

  const [status, setStatus] = useState<SocketStatus>("connecting");
  const [state, setState] = useState<RoomState | null>(null);
  const [lastEvent, setLastEvent] = useState<ServerEvent | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  // How far ahead the server's clock is, so every player's timer bar agrees.
  const offsetRef = useRef(0);

  const send = useCallback((type: string, payload: Record<string, unknown> = {}) => {
    const socket = socketRef.current;
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: `game_${type}`, payload }));
    }
  }, []);

  useEffect(() => {
    if (!enabled || !playerId || (!roomId && !code)) return;

    let cancelled = false;
    let attempt = 0;
    let socket: WebSocket | null = null;
    let reconnectTimer: number | undefined;
    let pingTimer: number | undefined;

    const connect = () => {
      if (cancelled) return;
      setStatus("connecting");
      socket = new WebSocket(socketUrl(playerId, playerName));
      socketRef.current = socket;

      socket.onopen = () => {
        if (cancelled) return;
        attempt = 0;
        setStatus("open");
        // Also how we come back after a drop: the server still holds our seat
        // and score, so joining again just reattaches the socket.
        socket?.send(
          JSON.stringify({
            type: "game_join",
            payload: roomId ? { roomId } : { code },
          }),
        );
        pingTimer = window.setInterval(() => {
          if (socket?.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: "game_ping", payload: {} }));
          }
        }, PING_INTERVAL);
      };

      socket.onmessage = (ev) => {
        if (cancelled) return;
        let msg: ServerEvent;
        try {
          msg = JSON.parse(ev.data as string);
        } catch {
          return;
        }
        const payload = msg.payload ?? {};
        if (typeof payload.serverNow === "number") {
          offsetRef.current = payload.serverNow - Date.now();
        }
        switch (msg.type) {
          case "room_state":
          case "question_end":
          case "game_over":
            // All three carry the full room state; the type only tells us what
            // just happened, so animations know when to fire.
            setState(payload as unknown as RoomState);
            setLastEvent(msg);
            break;
          case "error":
          case "answer_rejected":
            setNotice(String(payload.message ?? "That didn't work."));
            break;
          case "claim_rejected":
            // Both: the player needs telling, *and* the board needs to drop the
            // pending line it drew for this tap.
            setNotice(String(payload.message ?? "Someone got there first."));
            setLastEvent(msg);
            break;
          default:
            setLastEvent(msg);
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
      socketRef.current = null;
    };
  }, [enabled, playerId, playerName, roomId, code]);

  return {
    status,
    state,
    lastEvent,
    notice,
    clearNotice: useCallback(() => setNotice(null), []),
    /** Server time now, in ms — use instead of Date.now() for countdowns. */
    serverNow: useCallback(() => Date.now() + offsetRef.current, []),
    send,
  };
}
