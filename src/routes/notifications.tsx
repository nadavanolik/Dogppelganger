import { Link } from "react-router-dom";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { useSocketEvent } from "@/lib/appSocket";
import { notificationApi, notificationIcon, type Notification } from "@/lib/galleryApi";

export default NotifPage;

function NotifPage() {
  const [items, setItems] = useState<Notification[]>([]);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    notificationApi
      .list()
      .then((res) => setItems(res.items))
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Couldn't load your notifications."),
      );
  }, []);

  useEffect(load, [load]);
  useSocketEvent("notification", load);

  async function markAllRead() {
    await notificationApi.markAllRead();
    setItems((prev) => prev.map((n) => ({ ...n, read: true })));
  }

  return (
    <AppShell>
      <div className="max-w-2xl mx-auto">
        <div className="flex items-center justify-between mb-4">
          <h1 className="font-display text-4xl font-black">Notifications</h1>
          <button onClick={markAllRead} className="btn-pop btn-pop-hover bg-card px-3 py-1 text-sm">
            Mark all read
          </button>
        </div>
        {error && <div className="text-destructive text-sm mb-3">{error}</div>}
        <div className="space-y-2">
          {items.length === 0 && (
            <div className="card-pop p-8 text-center text-muted-foreground">
              Quiet in here. Go bark somewhere.
              {/* Chat messages are deliberately absent: they live in the
                  envelope badge and the inbox, not here. One row per message
                  would double the writes and split unread across two sources. */}
            </div>
          )}
          {items.map((n) => (
            <Link
              key={n.id}
              to={n.href ?? "/"}
              className={`card-pop-sm p-4 flex items-center gap-3 hover:-translate-y-0.5 transition ${
                n.read ? "opacity-70" : ""
              }`}
            >
              <div className="text-2xl">{notificationIcon(n.kind)}</div>
              <div className="flex-1">
                <div className="font-bold">{n.text}</div>
                <div className="text-xs text-muted-foreground">
                  {n.createdAt ? new Date(n.createdAt).toLocaleString() : ""}
                </div>
              </div>
              {!n.read && (
                <span className="h-3 w-3 rounded-full bg-primary border-2 border-[var(--ink)]" />
              )}
            </Link>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
