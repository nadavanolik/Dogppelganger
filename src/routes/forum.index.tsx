import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";

import { useSocketEvent } from "@/lib/appSocket";
import { useAuth } from "@/lib/auth";
import {
  forumApi,
  type ForumComment,
  type ForumPost,
  type ForumPostDeletedEvent,
  type ForumReactionEvent,
} from "@/lib/forumApi";
import { uploadImageUrl } from "@/lib/uploadApi";
import { MatchPair } from "@/components/MatchPair";

export default ForumList;

function ForumList() {
  const { user: me } = useAuth();
  const [posts, setPosts] = useState<ForumPost[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    forumApi
      .list()
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
  }, []);

  // Live updates. Everything below has already been written to the database by
  // the time it arrives — the socket carries a copy, not the only copy, so a
  // dropped frame costs a refresh and never a post.

  useSocketEvent("forum_post", (event) => {
    const post = event.payload as unknown as ForumPost;
    // Newest first, matching the server's ordering. Guarded because a
    // broadcast reaches the author's own tab too, and theirs may already have
    // it from the response to their POST.
    setPosts((prev) => (prev.some((p) => p.id === post.id) ? prev : [post, ...prev]));
  });

  useSocketEvent("forum_comment", (event) => {
    const comment = event.payload as unknown as ForumComment;
    setPosts((prev) =>
      prev.map((p) => (p.id === comment.postId ? { ...p, commentCount: p.commentCount + 1 } : p)),
    );
  });

  useSocketEvent("forum_reaction", (event) => {
    const summary = event.payload as unknown as ForumReactionEvent;
    if (summary.targetType !== "post") return; // comment thumbs live on the detail page
    setPosts((prev) =>
      prev.map((p) =>
        p.id === summary.targetId
          ? // `myReaction` is left alone on purpose: the counts are everyone's,
            // that value is only ever this browser's.
            { ...p, likeCount: summary.likeCount, dislikeCount: summary.dislikeCount }
          : p,
      ),
    );
  });

  useSocketEvent("forum_post_deleted", (event) => {
    const { id } = event.payload as unknown as ForumPostDeletedEvent;
    setPosts((prev) => prev.filter((p) => p.id !== id));
  });

  async function remove(post: ForumPost) {
    const warning = post.image
      ? "Delete this post? Its comments go too. Your photo stays on your profile."
      : "Delete this post? Its comments go too.";
    if (!window.confirm(warning)) return;
    await forumApi.removePost(post.id);
    setPosts((prev) => prev.filter((p) => p.id !== post.id));
  }

  async function react(post: ForumPost, kind: "like" | "dislike") {
    const summary = await forumApi.react("post", post.id, kind);
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
                  humanSrc={uploadImageUrl(p.image.jobId)}
                  dog={p.image.dog}
                  score={p.image.score}
                  showTraits={false}
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
              {p.authorId === me?.id && (
                <button
                  onClick={() => remove(p)}
                  className="btn-pop btn-pop-hover bg-card px-3 py-1 text-sm ml-auto text-destructive"
                >
                  🗑 Delete
                </button>
              )}
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
