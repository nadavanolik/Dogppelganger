import { Link } from "react-router-dom";
import { AppShell } from "@/components/AppShell";
import { DogCard } from "@/components/DogCard";
import { useStore } from "@/lib/store";

export default Index;

function Index() {
  const { state } = useStore();
  return <AppShell>{state.user ? <SignedInHome /> : <PublicLanding />}</AppShell>;
}

function PublicLanding() {
  const { state } = useStore();
  const shared = state.matches.filter((m) => m.shared && m.status === "done").slice(0, 6);
  return (
    <>
      <section className="grid md:grid-cols-2 gap-8 items-center">
        <div>
          <div className="inline-block px-3 py-1 rounded-full bg-mint border-2 border-[var(--ink)] text-sm font-bold">
            🐾 the great human-to-dog census
          </div>
          <h1 className="mt-4 font-display text-6xl md:text-7xl font-black leading-[0.95]">
            Find out what{" "}
            <span className="bg-primary text-primary-foreground px-2 rounded-2xl border-2 border-[var(--ink)] inline-block rotate-[-1.5deg]">
              dog
            </span>{" "}
            you actually are.
          </h1>
          <p className="mt-5 text-lg text-muted-foreground max-w-lg">
            Upload a selfie. Get your breed. Share it to the gallery, argue about it in the forum,
            DM your accidental Shiba twin, and play match games with the whole pack.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link
              to="/signup"
              className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-5 py-3 text-lg"
            >
              🐕 Sign up free
            </Link>
            <Link to="/login" className="btn-pop btn-pop-hover bg-sunshine px-5 py-3 text-lg">
              Log in
            </Link>
          </div>
          <div className="mt-6 flex items-center gap-2 text-sm text-muted-foreground">
            <span className="inline-flex -space-x-2">
              {["🧑", "👩", "🧔", "👵"].map((e, i) => (
                <span
                  key={i}
                  className="h-8 w-8 rounded-full bg-sunshine border-2 border-[var(--ink)] flex items-center justify-center"
                >
                  {e}
                </span>
              ))}
            </span>
            <span>{state.matches.filter((m) => m.shared).length}+ humans dogified this week</span>
          </div>
        </div>
        <div className="relative">
          <div className="card-pop p-6 rotate-[2deg]">
            <div className="text-sm font-bold text-muted-foreground mb-2">example match</div>
            <div className="flex items-center gap-4">
              <div className="h-32 w-32 rounded-2xl border-2 border-[var(--ink)] bg-sky flex items-center justify-center text-6xl">
                🧑
              </div>
              <div className="text-4xl">→</div>
              <div className="h-32 w-32 rounded-2xl border-2 border-[var(--ink)] bg-gradient-to-br from-amber-200 to-orange-300 flex items-center justify-center text-6xl">
                🐕
              </div>
            </div>
            <div className="mt-4 font-display text-2xl font-bold">Golden Retriever</div>
            <div className="text-muted-foreground italic">sunny optimist</div>
          </div>
          <div className="absolute -bottom-6 -left-6 card-pop-sm rotate-[-4deg] p-3 bg-bubblegum">
            <span className="text-sm font-bold">92% match ✨</span>
          </div>
        </div>
      </section>

      <section className="mt-16">
        <div className="flex items-end justify-between mb-4">
          <h2 className="font-display text-3xl font-black">A peek at the gallery</h2>
          <span className="text-sm text-muted-foreground italic">sign up to browse & react</span>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5 relative">
          {shared.map((m) => (
            <DogCard key={m.id} match={m} />
          ))}
        </div>
      </section>

      <section className="mt-16 grid md:grid-cols-3 gap-5">
        {[
          {
            emoji: "🎮",
            title: "Play match games",
            body: "Solo drills or live lobbies with friends.",
          },
          {
            emoji: "💬",
            title: "Argue in the forum",
            body: "Posts, comments, media, likes, dislikes.",
          },
          {
            emoji: "💌",
            title: "DM your match",
            body: "Slide into another dog's inbox. 1:1 with photos.",
          },
        ].map((c, i) => (
          <div key={i} className="card-pop p-6">
            <div className="text-5xl">{c.emoji}</div>
            <div className="mt-3 font-display text-2xl font-bold">{c.title}</div>
            <div className="text-muted-foreground mt-1">{c.body}</div>
          </div>
        ))}
      </section>

      <section className="mt-16 card-pop p-8 text-center bg-sunshine">
        <h2 className="font-display text-4xl font-black">Ready to meet your dog?</h2>
        <p className="text-muted-foreground mt-2">Free forever. Takes 30 seconds.</p>
        <div className="mt-4 flex gap-3 justify-center flex-wrap">
          <Link
            to="/signup"
            className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-6 py-3 text-lg"
          >
            Sign up
          </Link>
          <Link to="/login" className="btn-pop btn-pop-hover bg-card px-6 py-3 text-lg">
            I have an account
          </Link>
        </div>
      </section>
    </>
  );
}

function SignedInHome() {
  const { state } = useStore();
  const me = state.user!;
  const queue = state.matches.filter((m) => m.userId === me.id && m.status !== "done");
  const myNotifs = state.notifications.filter((n) => n.userId === me.id);
  const unreadDMs = myNotifs.filter((n) => n.kind === "dm" && !n.read).length;
  const unread = myNotifs.filter((n) => !n.read).length;

  const myPosts = state.posts.filter((p) => p.userId === me.id);
  const myComments = state.posts.flatMap((p) => p.comments.filter((c) => c.userId === me.id));
  const likesReceived =
    myPosts.reduce((n, p) => n + p.likes.length, 0) +
    myComments.reduce((n, c) => n + c.likes.length, 0);

  const recentPosts = [...state.posts].sort((a, b) => b.createdAt - a.createdAt).slice(0, 4);
  const galleryStrip = state.matches
    .filter((m) => m.shared && m.status === "done")
    .sort((a, b) => b.createdAt - a.createdAt)
    .slice(0, 6);

  return (
    <div className="space-y-10">
      <header>
        <div className="text-sm text-muted-foreground">Welcome back</div>
        <h1 className="font-display text-4xl md:text-5xl font-black">Hey, @{me.username} 🐾</h1>
      </header>

      <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MiniStat emoji="⏳" label="In queue" value={queue.length} />
        <MiniStat emoji="🔔" label="Unread alerts" value={unread} />
        <MiniStat emoji="💌" label="New DMs" value={unreadDMs} />
        <MiniStat emoji="❤️" label="Likes received" value={likesReceived} />
      </section>

      {queue.length > 0 && (
        <section className="card-pop p-5">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-xl font-black">Cooking now</h2>
            <Link to="/profile" className="text-xs underline">
              manage →
            </Link>
          </div>
          <ul className="mt-3 space-y-2">
            {queue.map((m) => (
              <li
                key={m.id}
                className="flex items-center gap-3 p-2 rounded-xl bg-muted border-2 border-[var(--ink)]"
              >
                <div className="text-2xl">{m.humanImg.length <= 4 ? m.humanImg : "🧑"}</div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-bold">
                    {m.urgent ? "🚨 Urgent" : "In queue"} · {m.status}
                  </div>
                  <div className="h-1.5 rounded-full bg-card border border-[var(--ink)] mt-1 overflow-hidden">
                    <div
                      className={`h-full ${m.status === "queued" ? "w-1/4 bg-sunshine" : "w-2/3 bg-primary animate-pulse"}`}
                    />
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="grid lg:grid-cols-2 gap-6">
        <div className="card-pop p-6">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-display text-2xl font-black">💬 Forum · latest</h2>
            <div className="flex gap-2">
              <Link
                to="/forum/new"
                className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-3 py-1 text-xs"
              >
                ＋ Post
              </Link>
              <Link to="/forum" className="text-xs underline self-center">
                all →
              </Link>
            </div>
          </div>
          <ul className="space-y-2">
            {recentPosts.map((p) => (
              <li key={p.id}>
                <Link
                  to={`/forum/${p.id}`}
                  className="block p-3 rounded-xl border-2 border-[var(--ink)] bg-card hover:bg-muted transition"
                >
                  <div className="font-bold truncate">{p.title}</div>
                  <div className="text-xs text-muted-foreground flex gap-3 mt-1">
                    <span>@{p.username}</span>
                    <span>💬 {p.comments.length}</span>
                    <span>👍 {p.likes.length}</span>
                  </div>
                </Link>
              </li>
            ))}
            {recentPosts.length === 0 && (
              <div className="text-sm text-muted-foreground">No posts yet.</div>
            )}
          </ul>
        </div>

        <div className="card-pop p-6">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-display text-2xl font-black">🖼 Gallery · fresh</h2>
            <Link to="/gallery" className="text-xs underline">
              browse all →
            </Link>
          </div>
          {galleryStrip.length === 0 ? (
            <div className="text-sm text-muted-foreground">
              No shared matches yet — share one from your profile.
            </div>
          ) : (
            <div className="grid grid-cols-3 gap-2">
              {galleryStrip.map((m) => (
                <div
                  key={m.id}
                  className={`aspect-square rounded-xl border-2 border-[var(--ink)] bg-gradient-to-br ${m.breedBg} flex flex-col items-center justify-center text-center p-1 relative overflow-hidden`}
                >
                  {m.breedImage ? (
                    <img
                      src={m.breedImage}
                      alt={m.breedName}
                      className="absolute inset-0 w-full h-full object-cover"
                    />
                  ) : (
                    <span className="text-4xl">{m.breedEmoji}</span>
                  )}
                  <span className="text-[10px] font-bold mt-1 truncate w-full z-10 bg-card/80 rounded px-1">
                    {m.breedName}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function MiniStat({ emoji, label, value }: { emoji: string; label: string; value: number }) {
  return (
    <div className="card-pop-sm p-3">
      <div className="text-2xl">{emoji}</div>
      <div className="text-xl font-display font-black">{value}</div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
    </div>
  );
}
