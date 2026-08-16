import { Link, useNavigate, useParams } from "react-router-dom";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { useStore } from "@/lib/store";
import { forumApi, type ForumComment, type PostWithComments } from "@/lib/forumApi";
import { uploadImageUrl } from "@/lib/uploadApi";

export default PostDetail;

function PostDetail() {
  const { id } = useParams();
  const { state, openConversation } = useStore();
  const owner = state.user ?? state.users[0];
  const navigate = useNavigate();

  const [post, setPost] = useState<PostWithComments | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [body, setBody] = useState("");
  const [posting, setPosting] = useState(false);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    forumApi
      .get(Number(id), owner.id)
      .then((row) => {
        if (!cancelled) setPost(row);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof Error && /404|doesn't exist/i.test(err.message)) setNotFound(true);
        else setLoadError(err instanceof Error ? err.message : "Couldn't load that post.");
      });
    return () => {
      cancelled = true;
    };
  }, [id, owner.id]);

  async function reactToPost(kind: "like" | "dislike") {
    if (!post) return;
    const summary = await forumApi.react(owner.id, "post", post.id, kind);
    setPost((p) => (p ? { ...p, ...summary } : p));
  }

  async function reactToComment(comment: ForumComment, kind: "like" | "dislike") {
    if (!post) return;
    const summary = await forumApi.react(owner.id, "comment", comment.id, kind);
    setPost((p) =>
      p
        ? {
            ...p,
            comments: p.comments.map((c) => (c.id === comment.id ? { ...c, ...summary } : c)),
          }
        : p,
    );
  }

  async function submitComment() {
    if (!post || !body.trim() || posting) return;
    setPosting(true);
    try {
      const comment = await forumApi.comment(post.id, owner.id, owner.username, body.trim());
      setPost((p) =>
        p ? { ...p, comments: [...p.comments, comment], commentCount: p.commentCount + 1 } : p,
      );
      setBody("");
    } finally {
      setPosting(false);
    }
  }

  if (notFound) {
    return (
      <AppShell>
        <div className="card-pop p-8 text-center">Post not found.</div>
      </AppShell>
    );
  }
  if (loadError) {
    return (
      <AppShell>
        <div className="card-pop p-8 text-center text-destructive">{loadError}</div>
      </AppShell>
    );
  }
  if (!post) {
    return (
      <AppShell>
        <div className="card-pop p-8 text-center text-muted-foreground">Loading…</div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="max-w-3xl mx-auto space-y-6">
        <Link to="/forum" className="text-sm underline">
          ← back to forum
        </Link>
        <article className="card-pop p-6">
          <div className="text-xs text-muted-foreground">
            @{post.authorName} · {post.createdAt ? new Date(post.createdAt).toLocaleString() : ""}
          </div>
          <p className="mt-3 whitespace-pre-wrap">{post.body}</p>
          {post.image && (
            <div className="mt-4 flex items-center gap-4">
              <img
                src={uploadImageUrl(post.authorId, post.image.jobId)}
                className="h-40 w-40 object-cover rounded-xl border-2 border-[var(--ink)]"
                alt={post.image.breedName ?? ""}
              />
              <div>
                <div className="font-display text-2xl font-bold">{post.image.breedName}</div>
                <div className="text-muted-foreground italic">{post.image.trait}</div>
              </div>
            </div>
          )}
          <div className="mt-4 flex items-center gap-2">
            <button
              onClick={() => reactToPost("like")}
              className={`btn-pop btn-pop-hover px-3 py-1 text-sm ${post.myReaction === "like" ? "bg-mint" : "bg-card"}`}
            >
              👍 {post.likeCount}
            </button>
            <button
              onClick={() => reactToPost("dislike")}
              className={`btn-pop btn-pop-hover px-3 py-1 text-sm ${post.myReaction === "dislike" ? "bg-destructive text-destructive-foreground" : "bg-card"}`}
            >
              👎 {post.dislikeCount}
            </button>
            {post.authorId !== owner.id && (
              <button
                onClick={() => {
                  const c = openConversation(post.authorId, post.authorName);
                  navigate(`/messages/${c.id}`);
                }}
                className="btn-pop btn-pop-hover bg-mint px-3 py-1 text-sm"
              >
                💌 DM @{post.authorName}
              </button>
            )}
          </div>
        </article>

        <section>
          <h2 className="font-display text-2xl font-bold mb-3">Comments · {post.commentCount}</h2>
          <div className="space-y-3">
            {post.comments.map((c) => (
              <div key={c.id} className="card-pop-sm p-4">
                <div className="text-xs text-muted-foreground">@{c.authorName}</div>
                <div className="mt-1 whitespace-pre-wrap">{c.body}</div>
                <div className="mt-2 flex gap-2">
                  <button
                    onClick={() => reactToComment(c, "like")}
                    className={`btn-pop btn-pop-hover px-2 py-1 text-xs ${c.myReaction === "like" ? "bg-mint" : "bg-card"}`}
                  >
                    👍 {c.likeCount}
                  </button>
                  <button
                    onClick={() => reactToComment(c, "dislike")}
                    className={`btn-pop btn-pop-hover px-2 py-1 text-xs ${c.myReaction === "dislike" ? "bg-destructive text-destructive-foreground" : "bg-card"}`}
                  >
                    👎 {c.dislikeCount}
                  </button>
                </div>
              </div>
            ))}
            {post.comments.length === 0 && (
              <div className="text-muted-foreground text-sm">No comments yet.</div>
            )}
          </div>

          <div className="card-pop p-4 mt-5">
            <div className="font-bold mb-2">Add a comment</div>
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="Bark your thoughts"
              rows={3}
              className="w-full rounded-xl border-2 border-[var(--ink)] px-3 py-2 bg-card"
            />
            <div className="mt-2 flex justify-end">
              <button
                disabled={!body.trim() || posting}
                onClick={submitComment}
                className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-4 py-1 disabled:opacity-50"
              >
                {posting ? "Posting…" : "Post comment"}
              </button>
            </div>
          </div>
        </section>
      </div>
    </AppShell>
  );
}
