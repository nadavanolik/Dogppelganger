import { createFileRoute, Link, useRouter } from "@tanstack/react-router";
import { useState } from "react";
import { AppShell, RequireAuth } from "@/components/AppShell";
import { useStore } from "@/lib/store";

export const Route = createFileRoute("/messages/")({ component: Inbox });

function Inbox() { return <AppShell><RequireAuth><Inner /></RequireAuth></AppShell>; }

function Inner() {
  const { state, openConversation } = useStore();
  const router = useRouter();
  const me = state.user!;
  const [q, setQ] = useState("");
  const mine = state.conversations.filter((c) => c.participants.includes(me.id));
  const otherUsers = state.users.filter((u) => u.id !== me.id && u.username.toLowerCase().includes(q.toLowerCase()));

  return (
    <div className="grid md:grid-cols-3 gap-6">
      <div className="md:col-span-2">
        <h1 className="font-display text-4xl font-black">Direct messages</h1>
        <p className="text-muted-foreground">Private 1:1 chats. Live, saved, ready to be weird in.</p>
        <div className="mt-5 space-y-3">
          {mine.length === 0 && <div className="card-pop p-6 text-muted-foreground">No conversations yet. Start one →</div>}
          {mine.map((c) => {
            const otherIdx = c.participants[0] === me.id ? 1 : 0;
            const otherName = c.usernames[otherIdx];
            const last = c.messages[c.messages.length - 1];
            return (
              <Link key={c.id} to={`/messages/${c.id}`} className="card-pop-sm p-4 flex items-center gap-3 hover:-translate-y-0.5 transition">
                <div className="h-12 w-12 rounded-2xl border-2 border-[var(--ink)] bg-bubblegum flex items-center justify-center text-2xl">🐕</div>
                <div className="flex-1">
                  <div className="font-bold">@{otherName}</div>
                  <div className="text-xs text-muted-foreground truncate">{last ? (last.body || "📎 attachment") : "No messages yet"}</div>
                </div>
                <div className="text-xs text-muted-foreground">{last ? new Date(last.at).toLocaleTimeString() : ""}</div>
              </Link>
            );
          })}
        </div>
      </div>
      <div className="card-pop p-5 h-fit">
        <div className="font-display text-xl font-black">Start a chat</div>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search users…" className="mt-3 w-full rounded-xl border-2 border-[var(--ink)] px-3 py-2 bg-card" />
        <div className="mt-3 space-y-2 max-h-72 overflow-auto">
          {otherUsers.map((u) => (
            <button
              key={u.id}
              onClick={() => { const c = openConversation(u.id, u.username); router.navigate({ to: `/messages/${c.id}` }); }}
              className="w-full text-left px-3 py-2 rounded-xl border-2 border-[var(--ink)] bg-card hover:bg-sunshine"
            >@{u.username}</button>
          ))}
          {otherUsers.length === 0 && <div className="text-sm text-muted-foreground">Nobody matches.</div>}
        </div>
      </div>
    </div>
  );
}
