import { Link, useParams } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import { AppShell, RequireAuth } from "@/components/AppShell";
import { useStore } from "@/lib/store";

export default DM;

function DM() {
  return (
    <AppShell>
      <RequireAuth>
        <Inner />
      </RequireAuth>
    </AppShell>
  );
}

function Inner() {
  const { id } = useParams();
  const { state, sendMessage } = useStore();
  const conv = state.conversations.find((c) => c.id === id);
  const [body, setBody] = useState("");
  const [media, setMedia] = useState<string | undefined>();
  const fi = useRef<HTMLInputElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight });
  }, [conv?.messages.length]);

  if (!conv)
    return (
      <div className="card-pop p-8 text-center">
        Conversation gone.{" "}
        <Link to="/messages" className="underline">
          Inbox
        </Link>
      </div>
    );
  const me = state.user!;
  const otherIdx = conv.participants[0] === me.id ? 1 : 0;
  const otherName = conv.usernames[otherIdx];

  return (
    <div className="max-w-2xl mx-auto card-pop flex flex-col h-[70vh]">
      <div className="p-4 border-b-2 border-[var(--ink)] flex items-center gap-3">
        <Link to="/messages" className="btn-pop btn-pop-hover bg-card px-2 py-1 text-sm">
          ←
        </Link>
        <div className="h-10 w-10 rounded-full bg-bubblegum border-2 border-[var(--ink)] flex items-center justify-center text-lg">
          🐕
        </div>
        <div>
          <div className="font-display font-bold">@{otherName}</div>
          <div className="text-xs text-muted-foreground">live · encrypted vibes</div>
        </div>
      </div>
      <div ref={scroller} className="flex-1 overflow-auto p-4 space-y-2 bg-muted/40">
        {conv.messages.length === 0 && (
          <div className="text-center text-muted-foreground text-sm py-8">Say hi 🐾</div>
        )}
        {conv.messages.map((m) => {
          const mine = m.from === me.id;
          return (
            <div key={m.id} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[75%] rounded-2xl px-3 py-2 border-2 border-[var(--ink)] ${mine ? "bg-primary text-primary-foreground rounded-br-sm" : "bg-card rounded-bl-sm"}`}
              >
                {m.body && <div className="whitespace-pre-wrap">{m.body}</div>}
                {m.media && <img src={m.media} className="mt-1 max-h-56 rounded-lg" />}
                <div
                  className={`text-[10px] mt-1 ${mine ? "text-primary-foreground/70" : "text-muted-foreground"}`}
                >
                  {new Date(m.at).toLocaleTimeString()}
                </div>
              </div>
            </div>
          );
        })}
      </div>
      <div className="p-3 border-t-2 border-[var(--ink)] flex gap-2 items-end">
        <button
          onClick={() => fi.current?.click()}
          className="btn-pop btn-pop-hover bg-sunshine px-3 py-2"
        >
          📎
        </button>
        <input
          ref={fi}
          type="file"
          accept="image/*,video/*"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (!f) return;
            const r = new FileReader();
            r.onload = () => setMedia(r.result as string);
            r.readAsDataURL(f);
          }}
        />
        <div className="flex-1">
          {media && (
            <div className="relative mb-1 inline-block">
              <img src={media} className="max-h-24 rounded-lg border-2 border-[var(--ink)]" />
              <button
                onClick={() => setMedia(undefined)}
                className="absolute -top-2 -right-2 h-6 w-6 rounded-full bg-card border-2 border-[var(--ink)] text-xs"
              >
                ×
              </button>
            </div>
          )}
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder="Type a bark…"
            rows={1}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (body.trim() || media) {
                  sendMessage(conv.id, body.trim(), media);
                  setBody("");
                  setMedia(undefined);
                }
              }
            }}
            className="w-full rounded-xl border-2 border-[var(--ink)] px-3 py-2 bg-card resize-none"
          />
        </div>
        <button
          onClick={() => {
            if (body.trim() || media) {
              sendMessage(conv.id, body.trim(), media);
              setBody("");
              setMedia(undefined);
            }
          }}
          className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-4 py-2"
        >
          Send
        </button>
      </div>
    </div>
  );
}
