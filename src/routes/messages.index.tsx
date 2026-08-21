import { Link, useNavigate } from "react-router-dom";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { useSocketEvent } from "@/lib/appSocket";
import { dmApi, userApi, type DirectoryUser, type DmConversation } from "@/lib/dmApi";

export default Inbox;

function Inbox() {
  const navigate = useNavigate();
  const [conversations, setConversations] = useState<DmConversation[]>([]);
  const [query, setQuery] = useState("");
  const [people, setPeople] = useState<DirectoryUser[]>([]);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    dmApi
      .conversations()
      .then(setConversations)
      .catch((err) => setError(err instanceof Error ? err.message : "Couldn't load your chats."));
  }, []);

  useEffect(load, [load]);

  // A new message anywhere reorders the inbox and moves the unread badge.
  useSocketEvent("dm_received", load);
  useSocketEvent("dm_sent", load);

  // The directory replaces a list of every seeded mock account. It returns
  // usernames only — never email addresses.
  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(() => {
      userApi
        .search(query)
        .then((rows) => !cancelled && setPeople(rows))
        .catch(() => {});
    }, 200);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query]);

  async function openWith(userId: number) {
    try {
      const conv = await dmApi.open(userId);
      navigate(`/messages/${conv.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't open that chat.");
    }
  }

  return (
    <AppShell>
      <div className="grid md:grid-cols-3 gap-6">
        <div className="md:col-span-2">
          <h1 className="font-display text-4xl font-black">Direct messages</h1>
          <p className="text-muted-foreground">
            Private 1:1 chats. Live, saved, ready to be weird in.
          </p>
          {error && <div className="mt-3 text-destructive text-sm">{error}</div>}
          <div className="mt-5 space-y-3">
            {conversations.length === 0 && (
              <div className="card-pop p-6 text-muted-foreground">
                No conversations yet. Start one →
              </div>
            )}
            {conversations.map((c) => (
              <Link
                key={c.id}
                to={`/messages/${c.id}`}
                className="card-pop-sm p-4 flex items-center gap-3 hover:-translate-y-0.5 transition"
              >
                <div className="h-12 w-12 rounded-2xl border-2 border-[var(--ink)] bg-bubblegum flex items-center justify-center text-2xl">
                  🐕
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-bold">@{c.other.username}</div>
                  <div className="text-xs text-muted-foreground truncate">{preview(c)}</div>
                </div>
                {c.unreadCount > 0 && (
                  <span className="inline-flex items-center justify-center rounded-full bg-primary text-primary-foreground text-xs h-6 min-w-6 px-2 border-2 border-[var(--ink)]">
                    {c.unreadCount}
                  </span>
                )}
              </Link>
            ))}
          </div>
        </div>
        <div className="card-pop p-5 h-fit">
          <div className="font-display text-xl font-black">Start a chat</div>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search users…"
            className="mt-3 w-full rounded-xl border-2 border-[var(--ink)] px-3 py-2 bg-card"
          />
          <div className="mt-3 space-y-2 max-h-72 overflow-auto">
            {people.map((u) => (
              <button
                key={u.id}
                onClick={() => openWith(u.id)}
                className="w-full text-left px-3 py-2 rounded-xl border-2 border-[var(--ink)] bg-card hover:bg-sunshine"
              >
                @{u.username}
              </button>
            ))}
            {people.length === 0 && (
              <div className="text-sm text-muted-foreground">Nobody matches.</div>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}

/**
 * The one-line summary in the list.
 *
 * A video has no thumbnail to show — there is no server-side transcode, so
 * there is no poster frame, and loading a 25MB clip to draw a 40px preview
 * would be worse than a label.
 */
function preview(c: DmConversation): string {
  const last = c.lastMessage;
  if (!last) return "No messages yet";
  if (last.body) return last.body;
  if (last.attachment?.kind === "video") return "🎬 Video";
  if (last.attachment?.kind === "image") return "🖼 Photo";
  return "📎 Attachment";
}
