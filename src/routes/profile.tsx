import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { AppShell, RequireAuth } from "@/components/AppShell";
import { DogCard } from "@/components/DogCard";
import { useStore } from "@/lib/store";

export const Route = createFileRoute("/profile")({ component: Profile });

function Profile() {
  return (
    <AppShell>
      <RequireAuth>
        <Inner />
      </RequireAuth>
    </AppShell>
  );
}

type Filter = "all" | "shared" | "private";

function Inner() {
  const { state, shareMatch, discardMatch } = useStore();
  const me = state.user!;
  const [filter, setFilter] = useState<Filter>("all");

  const mine = state.matches.filter((m) => m.userId === me.id);
  const done = mine.filter((m) => m.status === "done");
  const shared = done.filter((m) => m.shared);
  const privateDogs = done.filter((m) => !m.shared);

  const myPosts = state.posts.filter((p) => p.userId === me.id);
  const myComments = state.posts.flatMap((p) => p.comments.filter((c) => c.userId === me.id));
  const likesReceived =
    myPosts.reduce((n, p) => n + p.likes.length, 0) + myComments.reduce((n, c) => n + c.likes.length, 0);
  const dislikesReceived =
    myPosts.reduce((n, p) => n + p.dislikes.length, 0) + myComments.reduce((n, c) => n + c.dislikes.length, 0);

  const visible = filter === "shared" ? shared : filter === "private" ? privateDogs : done;

  return (
    <div className="space-y-8">
      <header className="card-pop p-6 flex flex-wrap items-center gap-4">
        <div className="h-16 w-16 rounded-full bg-sunshine border-2 border-[var(--ink)] flex items-center justify-center text-3xl shrink-0">🧑</div>
        <div className="min-w-0">
          <div className="text-xs text-muted-foreground">Profile</div>
          <h1 className="font-display text-4xl font-black truncate">@{me.username}</h1>
          <div className="text-sm text-muted-foreground">{me.email}</div>
        </div>
      </header>

      <div className="grid md:grid-cols-4 gap-4">
        <Stat emoji="🐕" label="Total dogs" value={done.length} />
        <Stat emoji="📣" label="Shared" value={shared.length} />
        <Stat emoji="✍️" label="Forum posts" value={myPosts.length} />
        <Stat emoji="👍/👎" label="Reactions received" value={`${likesReceived} / ${dislikesReceived}`} />
      </div>

      <section>
        <div className="flex flex-wrap items-end justify-between gap-3 mb-3">
          <h2 className="font-display text-3xl font-black">My dogs</h2>
          <Link to="/upload" className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-4 py-2 text-sm">＋ New match</Link>
        </div>

        <div className="flex gap-2 mb-4 flex-wrap">
          <Tab active={filter === "all"} onClick={() => setFilter("all")}>All ({done.length})</Tab>
          <Tab active={filter === "shared"} onClick={() => setFilter("shared")}>Shared ({shared.length})</Tab>
          <Tab active={filter === "private"} onClick={() => setFilter("private")}>Private ({privateDogs.length})</Tab>
        </div>

        {visible.length === 0 ? (
          <div className="card-pop p-8 text-center text-muted-foreground">
            {done.length === 0 ? (
              <>No matches yet. <Link to="/upload" className="underline">Upload one →</Link></>
            ) : (
              <>Nothing in this bucket.</>
            )}
          </div>
        ) : (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {visible.map((m) => (
              <div key={m.id} className="relative">
                <DogCard match={m} />
                <div className="absolute top-2 right-2 flex gap-1">
                  {m.shared ? (
                    <span className="text-xs bg-mint px-2 py-1 rounded-full border-2 border-[var(--ink)] font-bold">shared</span>
                  ) : (
                    <button onClick={() => shareMatch(m.id)} className="text-xs bg-primary text-primary-foreground px-2 py-1 rounded-full border-2 border-[var(--ink)] font-bold">share</button>
                  )}
                  <button onClick={() => discardMatch(m.id)} className="text-xs bg-card px-2 py-1 rounded-full border-2 border-[var(--ink)]">🗑</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function Tab({ active, children, onClick }: { active: boolean; children: React.ReactNode; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`btn-pop btn-pop-hover px-4 py-1.5 text-sm ${active ? "bg-primary text-primary-foreground" : "bg-card"}`}
    >
      {children}
    </button>
  );
}

function Stat({ emoji, label, value }: { emoji: string; label: string; value: number | string }) {
  return (
    <div className="card-pop-sm p-4">
      <div className="text-3xl">{emoji}</div>
      <div className="text-2xl font-display font-black mt-1">{value}</div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </div>
  );
}
