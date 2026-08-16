/**
 * Live `upload_update` events for the signed-in owner's queued jobs — powers
 * the live status in the upload panel with no polling. Mirrors gameSocket's
 * reconnect-with-backoff behavior, but this socket is receive-only.
 */
import { useEffect, useRef } from "react";
import type { UploadJob } from "./uploadApi";

// nginx closes an idle proxied connection after 60s, so keep it warm.
const PING_INTERVAL = 25_000;
const MAX_BACKOFF = 8_000;

function socketUrl(ownerId: string): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/api/uploads/ws?ownerId=${encodeURIComponent(ownerId)}`;
}

export function useUploadNotifications(ownerId: string | null, onUpdate: (job: UploadJob) => void) {
  const onUpdateRef = useRef(onUpdate);
  onUpdateRef.current = onUpdate;

  useEffect(() => {
    if (!ownerId) return;

    let cancelled = false;
    let attempt = 0;
    let socket: WebSocket | null = null;
    let reconnectTimer: number | undefined;
    let pingTimer: number | undefined;

    const connect = () => {
      if (cancelled) return;
      socket = new WebSocket(socketUrl(ownerId));

      socket.onopen = () => {
        if (cancelled) return;
        attempt = 0;
        pingTimer = window.setInterval(() => {
          if (socket?.readyState === WebSocket.OPEN) socket.send("ping");
        }, PING_INTERVAL);
      };

      socket.onmessage = (ev) => {
        if (cancelled) return;
        try {
          const msg = JSON.parse(ev.data as string);
          if (msg?.type === "upload_update") onUpdateRef.current(msg.payload as UploadJob);
        } catch {
          // ignore malformed frames
        }
      };

      socket.onclose = () => {
        window.clearInterval(pingTimer);
        if (cancelled) return;
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
  }, [ownerId]);
}
