import { Link } from "react-router-dom";
import { AppShell } from "@/components/AppShell";
import { useStore } from "@/lib/store";

export default ForumList;

function ForumList() {
  const { state, toggleReact } = useStore();
  return (
    <AppShell>
      <div className="flex items-end justify-between">
        <div>
          <h1 className="font-display text-5xl font-black">Forum</h1>
          <p className="text-muted-foreground">Post opinions, defend breeds, escalate to lore.</p>
        </div>
        <Link
          to="/forum/new"
          className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-5 py-2"
        >
          ✍️ New post
        </Link>
      </div>
      <div className="mt-6 space-y-4">
        {state.posts.map((p) => (
          <article key={p.id} className="card-pop-sm p-5">
            <div className="text-xs text-muted-foreground">
              @{p.username} · {new Date(p.createdAt).toLocaleString()}
            </div>
            <Link
              to={`/forum/${p.id}`}
              className="font-display text-2xl font-bold mt-1 block hover:underline"
            >
              {p.title}
            </Link>
            <p className="text-muted-foreground mt-1 line-clamp-2">{p.body}</p>
            {p.media && (
              <img
                src={p.media}
                className="mt-3 max-h-64 rounded-xl border-2 border-[var(--ink)]"
                alt=""
              />
            )}
            <div className="mt-3 flex items-center gap-2">
              <button
                onClick={() => toggleReact({ postId: p.id }, "likes")}
                className="btn-pop btn-pop-hover bg-card px-3 py-1 text-sm"
              >
                👍 {p.likes.length}
              </button>
              <button
                onClick={() => toggleReact({ postId: p.id }, "dislikes")}
                className="btn-pop btn-pop-hover bg-card px-3 py-1 text-sm"
              >
                👎 {p.dislikes.length}
              </button>
              <Link
                to={`/forum/${p.id}`}
                className="btn-pop btn-pop-hover bg-sunshine px-3 py-1 text-sm"
              >
                💬 {p.comments.length}
              </Link>
            </div>
          </article>
        ))}
      </div>
    </AppShell>
  );
}
