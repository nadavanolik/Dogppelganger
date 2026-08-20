import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { useStore } from "@/lib/store";
import { forumApi, type ForumPost } from "@/lib/forumApi";
import { uploadImageUrl } from "@/lib/uploadApi";
import { MatchPair } from "@/components/MatchPair";

export default ForumList;

function ForumList() {
  const { state } = useStore();
  const owner = state.user ?? state.users[0];
  const [posts, setPosts] = useState<ForumPost[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    forumApi
      .list(owner.id)
      .then((rows) => {
        if (!cancelled) setPosts(rows);
      })
      .catch((err) => {
        if (!cancelled)
          setLoadError(err instanceof Error ? err.message : "Couldn't load the forum.");
      });
    return () => {
      cancelled = true;
    };
  }, [owner.id]);

  async function react(post: ForumPost, kind: "like" | "dislike") {
    const summary = await forumApi.react(owner.id, "post", post.id, kind);
    setPosts((prev) => prev.map((p) => (p.id === post.id ? { ...p, ...summary } : p)));
  }

  return (
    <AppShell>
      <div className="flex items-end justify-between">
        <div>
          <h1 className="font-display text-5xl font-black">Forum</h1>
          <p className="text-muted-foreground">Post opinions, share your dogs, escalate to lore.</p>
        </div>
        <Link
          to="/forum/new"
          className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-5 py-2"
        >
          ✍️ New post
        </Link>
      </div>

      {loadError && <div className="mt-6 text-sm text-destructive">{loadError}</div>}

      <div className="mt-6 space-y-4">
        {posts.map((p) => (
          <article key={p.id} className="card-pop-sm p-5">
            <div className="text-xs text-muted-foreground">
              @{p.authorName} · {p.createdAt ? new Date(p.createdAt).toLocaleString() : ""}
            </div>
            <Link
              to={`/forum/${p.id}`}
              className="text-muted-foreground mt-1 line-clamp-2 block hover:underline"
            >
              {p.body}
            </Link>
            {p.image && (
              <div className="mt-3">
                <MatchPair
                  humanSrc={uploadImageUrl(p.authorId, p.image.jobId)}
                  dog={p.image.dog}
                  score={p.image.score}
                  sharedTraits={p.image.sharedTraits}
                />
              </div>
            )}
            <div className="mt-3 flex items-center gap-2">
              <button
                onClick={() => react(p, "like")}
                className={`btn-pop btn-pop-hover px-3 py-1 text-sm ${p.myReaction === "like" ? "bg-mint" : "bg-card"}`}
              >
                👍 {p.likeCount}
              </button>
              <button
                onClick={() => react(p, "dislike")}
                className={`btn-pop btn-pop-hover px-3 py-1 text-sm ${p.myReaction === "dislike" ? "bg-destructive text-destructive-foreground" : "bg-card"}`}
              >
                👎 {p.dislikeCount}
              </button>
              <Link
                to={`/forum/${p.id}`}
                className="btn-pop btn-pop-hover bg-sunshine px-3 py-1 text-sm"
              >
                💬 {p.commentCount}
              </Link>
            </div>
          </article>
        ))}
        {!loadError && posts.length === 0 && (
          <div className="card-pop p-8 text-center text-muted-foreground">
            No posts yet. Be the first to share a dog.
          </div>
        )}
      </div>
    </AppShell>
  );
}
