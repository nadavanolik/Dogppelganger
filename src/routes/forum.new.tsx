import { createFileRoute, useRouter } from "@tanstack/react-router";
import { useRef, useState } from "react";
import { AppShell, RequireAuth } from "@/components/AppShell";
import { useStore } from "@/lib/store";

export const Route = createFileRoute("/forum/new")({ component: NewPost });

function NewPost() {
  return <AppShell><RequireAuth><Inner /></RequireAuth></AppShell>;
}

function Inner() {
  const { addPost } = useStore();
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [media, setMedia] = useState<string | undefined>();
  const fi = useRef<HTMLInputElement>(null);
  return (
    <div className="max-w-2xl mx-auto card-pop p-6">
      <h1 className="font-display text-3xl font-black">New post</h1>
      <div className="mt-4 space-y-3">
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Give it a punchy title" className="w-full rounded-xl border-2 border-[var(--ink)] px-3 py-2 bg-card text-lg font-bold" />
        <textarea value={body} onChange={(e) => setBody(e.target.value)} placeholder="Say your piece" rows={6} className="w-full rounded-xl border-2 border-[var(--ink)] px-3 py-2 bg-card" />
        {media && <div className="relative"><img src={media} className="max-h-64 rounded-xl border-2 border-[var(--ink)]" /><button onClick={() => setMedia(undefined)} className="absolute top-2 right-2 btn-pop bg-card px-2 py-1 text-xs">remove</button></div>}
        <div className="flex justify-between gap-2">
          <button type="button" onClick={() => fi.current?.click()} className="btn-pop btn-pop-hover bg-sunshine px-4 py-2">📎 Attach image/video</button>
          <input ref={fi} type="file" accept="image/*,video/*" className="hidden" onChange={(e) => {
            const f = e.target.files?.[0]; if (!f) return;
            const r = new FileReader(); r.onload = () => setMedia(r.result as string); r.readAsDataURL(f);
          }} />
          <button
            disabled={!title.trim() || !body.trim()}
            onClick={() => { const p = addPost(title.trim(), body.trim(), media); router.navigate({ to: `/forum/${p.id}` }); }}
            className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-5 py-2 disabled:opacity-50"
          >Publish</button>
        </div>
      </div>
    </div>
  );
}
