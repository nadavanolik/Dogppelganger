import { Link, useParams } from "react-router-dom";
import { useCallback, useEffect, useRef, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { useSocketEvent } from "@/lib/appSocket";
import { attachmentUrl, dmApi, type DmConversation, type DmMessage } from "@/lib/dmApi";

export default DM;

const MAX_IMAGE_MB = 10;
const MAX_VIDEO_MB = 25;

function DM() {
  const { id } = useParams();
  const conversationId = Number(id);
  const [conversation, setConversation] = useState<DmConversation | null>(null);
  const [messages, setMessages] = useState<DmMessage[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [body, setBody] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [sending, setSending] = useState(false);
  const filePicker = useRef<HTMLInputElement>(null);
  const scroller = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    try {
      const [convs, page] = await Promise.all([
        dmApi.conversations(),
        dmApi.history(conversationId),
      ]);
      setConversation(convs.find((c) => c.id === conversationId) ?? null);
      // The API returns newest first (it pages backwards); the transcript reads
      // oldest at the top.
      setMessages([...page.messages].reverse());
      setHasMore(page.hasMore);
      // Opening the thread is what marks it read.
      await dmApi.markRead(conversationId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't load that conversation.");
    } finally {
      setLoading(false);
    }
  }, [conversationId]);

  useEffect(() => {
    if (!Number.isFinite(conversationId)) return;
    setLoading(true);
    load();
  }, [conversationId, load]);

  // Live delivery. The message is already saved by the time this arrives — the
  // socket carries a copy, not the only copy.
  useSocketEvent("dm_received", (event) => {
    const message = event.payload as unknown as DmMessage;
    if (message.conversationId !== conversationId) return;
    setMessages((prev) => (prev.some((m) => m.id === message.id) ? prev : [...prev, message]));
    dmApi.markRead(conversationId).catch(() => {});
  });

  // The same message typed on another device of yours.
  useSocketEvent("dm_sent", (event) => {
    const message = event.payload as unknown as DmMessage;
    if (message.conversationId !== conversationId) return;
    setMessages((prev) => (prev.some((m) => m.id === message.id) ? prev : [...prev, message]));
  });

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight });
  }, [messages.length]);

  async function loadOlder() {
    if (messages.length === 0) return;
    const page = await dmApi.history(conversationId, messages[0].id);
    setMessages((prev) => [...[...page.messages].reverse(), ...prev]);
    setHasMore(page.hasMore);
  }

  async function submit() {
    if (sending || (!body.trim() && !file)) return;
    setSending(true);
    setError("");
    try {
      const sent = await dmApi.send(conversationId, body.trim(), file);
      setMessages((prev) => (prev.some((m) => m.id === sent.id) ? prev : [...prev, sent]));
      setBody("");
      setFile(null);
      if (filePicker.current) filePicker.current.value = "";
    } catch (err) {
      setError(err instanceof Error ? err.message : "That didn't send.");
    } finally {
      setSending(false);
    }
  }

  if (loading) return null;

  if (!conversation) {
    return (
      <AppShell>
        <div className="card-pop p-8 text-center">
          Conversation gone.{" "}
          <Link to="/messages" className="underline">
            Inbox
          </Link>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="max-w-2xl mx-auto card-pop flex flex-col h-[70vh]">
        <div className="p-4 border-b-2 border-[var(--ink)] flex items-center gap-3">
          <Link to="/messages" className="btn-pop btn-pop-hover bg-card px-2 py-1 text-sm">
            ←
          </Link>
          <div className="h-10 w-10 rounded-full bg-bubblegum border-2 border-[var(--ink)] flex items-center justify-center text-lg">
            🐕
          </div>
          <div>
            <div className="font-display font-bold">@{conversation.other.username}</div>
            <div className="text-xs text-muted-foreground">
              {conversation.canReply ? "live · saved forever" : "this account was deleted"}
            </div>
          </div>
        </div>

        <div ref={scroller} className="flex-1 overflow-auto p-4 space-y-2 bg-muted/40">
          {hasMore && (
            <button onClick={loadOlder} className="mx-auto block text-xs underline">
              Load older messages
            </button>
          )}
          {messages.length === 0 && (
            <div className="text-center text-muted-foreground text-sm py-8">Say hi 🐾</div>
          )}
          {messages.map((m) => (
            <Bubble key={m.id} message={m} />
          ))}
        </div>

        {error && <div className="px-4 py-2 text-destructive text-sm">{error}</div>}

        {conversation.canReply ? (
          <div className="p-3 border-t-2 border-[var(--ink)] flex gap-2 items-end">
            <button
              onClick={() => filePicker.current?.click()}
              className="btn-pop btn-pop-hover bg-sunshine px-3 py-2"
              title={`Image up to ${MAX_IMAGE_MB}MB, video up to ${MAX_VIDEO_MB}MB`}
            >
              📎
            </button>
            <input
              ref={filePicker}
              type="file"
              accept="image/jpeg,image/png,image/webp,video/mp4,video/webm"
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            <div className="flex-1">
              {file && (
                <div className="mb-1 inline-flex items-center gap-2 text-xs border-2 border-[var(--ink)] rounded-lg px-2 py-1 bg-card">
                  <span className="truncate max-w-[16rem]">{file.name}</span>
                  <button onClick={() => setFile(null)} className="font-bold">
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
                    submit();
                  }
                }}
                className="w-full rounded-xl border-2 border-[var(--ink)] px-3 py-2 bg-card resize-none"
              />
            </div>
            <button
              onClick={submit}
              disabled={sending}
              className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-4 py-2 disabled:opacity-60"
            >
              {sending ? "…" : "Send"}
            </button>
          </div>
        ) : (
          <div className="p-4 border-t-2 border-[var(--ink)] text-sm text-muted-foreground text-center">
            You can still read this conversation, but there's nobody left to reply to.
          </div>
        )}
      </div>
    </AppShell>
  );
}

function Bubble({ message }: { message: DmMessage }) {
  const mine = message.mine;
  return (
    <div className={`flex ${mine ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[75%] rounded-2xl px-3 py-2 border-2 border-[var(--ink)] ${
          mine ? "bg-primary text-primary-foreground rounded-br-sm" : "bg-card rounded-bl-sm"
        }`}
      >
        {message.body && <div className="whitespace-pre-wrap">{message.body}</div>}
        <Attachment message={message} />
        <div
          className={`text-[10px] mt-1 ${
            mine ? "text-primary-foreground/70" : "text-muted-foreground"
          }`}
        >
          {message.createdAt ? new Date(message.createdAt).toLocaleTimeString() : ""}
        </div>
      </div>
    </div>
  );
}

function Attachment({ message }: { message: DmMessage }) {
  if (!message.attachment) return null;

  if (message.attachment.kind === "video") {
    return (
      // `preload="metadata"` plus the `#t=0.1` fragment on the URL is what
      // gives a video bubble a first frame instead of a black rectangle. There
      // is no server-generated poster: transcoding would mean shipping ffmpeg,
      // which is a lot of image and CPU for a chat attachment.
      <video
        src={attachmentUrl(message) ?? undefined}
        controls
        playsInline
        preload="metadata"
        className="mt-1 max-h-64 rounded-lg border-2 border-[var(--ink)]"
      />
    );
  }

  return (
    <img
      src={attachmentUrl(message) ?? undefined}
      alt={message.attachment.name ?? "attachment"}
      className="mt-1 max-h-56 rounded-lg border-2 border-[var(--ink)]"
    />
  );
}
