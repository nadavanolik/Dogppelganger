import { createFileRoute, Link, useRouter } from "@tanstack/react-router";
import { useRef, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { useStore } from "@/lib/store";

export const Route = createFileRoute("/forum/$id")({ component: PostDetail });

function PostDetail() {
  const { id } = Route.useParams();
  const { state, toggleReact, addComment, openConversation } = useStore();
  const router = useRouter();
  const post = state.posts.find((p) => p.id === id);
  const [body, setBody] = useState("");
  const [media, setMedia] = useState<string | undefined>();
  const fi = useRef<HTMLInputElement>(null);

  if (!post) return <AppShell><div className="card-pop p-8 text-center">Post not found.</div></AppShell>;

  return (
    <AppShell>
      <div className="max-w-3xl mx-auto space-y-6">
        <Link to="/forum" className="text-sm underline">← back to forum</Link>
        <article className="card-pop p-6">
          <div className="text-xs text-muted-foreground">
            @{post.username} · {new Date(post.createdAt).toLocaleString()}
          </div>
          <h1 className="font-display text-4xl font-black mt-1">{post.title}</h1>
          <p className="mt-3 whitespace-pre-wrap">{post.body}</p>
          {post.media && <img src={post.media} className="mt-4 rounded-xl border-2 border-[var(--ink)]" alt="" />}
          <div className="mt-4 flex items-center gap-2">
            <button onClick={() => toggleReact({ postId: post.id }, "likes")} className="btn-pop btn-pop-hover bg-card px-3 py-1 text-sm">👍 {post.likes.length}</button>
            <button onClick={() => toggleReact({ postId: post.id }, "dislikes")} className="btn-pop btn-pop-hover bg-card px-3 py-1 text-sm">👎 {post.dislikes.length}</button>
            {state.user && post.userId !== state.user.id && (
              <button
                onClick={() => {
                  const c = openConversation(post.userId, post.username);
                  router.navigate({ to: `/messages/${c.id}` });
                }}
                className="btn-pop btn-pop-hover bg-mint px-3 py-1 text-sm"
              >💌 DM @{post.username}</button>
            )}
          </div>
        </article>

        <section>
          <h2 className="font-display text-2xl font-bold mb-3">Comments · {post.comments.length}</h2>
          <div className="space-y-3">
            {post.comments.map((c) => (
              <div key={c.id} className="card-pop-sm p-4">
                <div className="text-xs text-muted-foreground">@{c.username}</div>
                <div className="mt-1 whitespace-pre-wrap">{c.body}</div>
                {c.media && <img src={c.media} className="mt-2 max-h-56 rounded-lg border-2 border-[var(--ink)]" alt="" />}
                <div className="mt-2 flex gap-2">
                  <button onClick={() => toggleReact({ postId: post.id, commentId: c.id }, "likes")} className="btn-pop btn-pop-hover bg-card px-2 py-1 text-xs">👍 {c.likes.length}</button>
                  <button onClick={() => toggleReact({ postId: post.id, commentId: c.id }, "dislikes")} className="btn-pop btn-pop-hover bg-card px-2 py-1 text-xs">👎 {c.dislikes.length}</button>
                </div>
              </div>
            ))}
            {post.comments.length === 0 && <div className="text-muted-foreground text-sm">No comments yet.</div>}
          </div>

          <div className="card-pop p-4 mt-5">
            <div className="font-bold mb-2">Add a comment</div>
            <textarea value={body} onChange={(e) => setBody(e.target.value)} placeholder="Bark your thoughts" rows={3} className="w-full rounded-xl border-2 border-[var(--ink)] px-3 py-2 bg-card" />
            {media && <img src={media} className="max-h-40 rounded-xl border-2 border-[var(--ink)] mt-2" />}
            <div className="mt-2 flex justify-between">
              <button type="button" onClick={() => fi.current?.click()} className="btn-pop btn-pop-hover bg-sunshine px-3 py-1 text-sm">📎 attach</button>
              <input ref={fi} type="file" accept="image/*,video/*" className="hidden" onChange={(e) => {
                const f = e.target.files?.[0]; if (!f) return;
                const r = new FileReader(); r.onload = () => setMedia(r.result as string); r.readAsDataURL(f);
              }} />
              <button
                disabled={!body.trim() || !state.user}
                onClick={() => { addComment(post.id, body.trim(), media); setBody(""); setMedia(undefined); }}
                className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-4 py-1 disabled:opacity-50"
              >Post comment</button>
            </div>
            {!state.user && <div className="text-xs text-muted-foreground mt-2"><Link to="/login" className="underline">Log in</Link> to comment.</div>}
          </div>
        </section>
      </div>
    </AppShell>
  );
}
