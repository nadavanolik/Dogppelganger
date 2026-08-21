import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { SharedTraits } from "@/components/MatchPair";
import { useAuth } from "@/lib/auth";
import { forumApi, type ForumPost } from "@/lib/forumApi";
import { uploadApi, uploadImageUrl, type UploadJob } from "@/lib/uploadApi";
import { useUploadFeed } from "@/lib/uploadFeed";

export default Profile;

function Profile() {
  return (
    <AppShell>
      <Inner />
    </AppShell>
  );
}

type Filter = "all" | "done" | "cooking";

const STATUS_LABEL: Record<string, string> = {
  queued: "⏳ queued",
  processing: "🐾 finding your dog",
  done: "✅ done",
  error: "⚠️ error",
};

function Inner() {
  const { user } = useAuth();
  const { jobs, loading, error } = useUploadFeed();
  const me = user!;
  const [filter, setFilter] = useState<Filter>("all");

  // Every match, straight from the server. This used to read the localStorage
  // mock, so a dog you actually made never appeared here and one you never
  // made always did.
  const done = jobs.filter((j) => j.status === "done");
  const cooking = jobs.filter((j) => j.status === "queued" || j.status === "processing");

  // Forum stats from the server. These used to be computed over a localStorage
  // array, so they counted posts nobody else could see and missed every real one.
  const [myPosts, setMyPosts] = useState<ForumPost[]>([]);
  useEffect(() => {
    forumApi
      .byAuthor(me.id)
      .then(setMyPosts)
      .catch(() => {});
  }, [me.id]);
  const likesReceived = myPosts.reduce((n, p) => n + p.likeCount, 0);
  const dislikesReceived = myPosts.reduce((n, p) => n + p.dislikeCount, 0);

  const visible = filter === "done" ? done : filter === "cooking" ? cooking : jobs;

  return (
    <div className="space-y-8">
      <header className="card-pop p-6 flex flex-wrap items-center gap-4">
        <div className="h-16 w-16 rounded-full bg-sunshine border-2 border-[var(--ink)] flex items-center justify-center text-3xl shrink-0">
          🧑
        </div>
        <div className="min-w-0">
          <div className="text-xs text-muted-foreground">Profile</div>
          <h1 className="font-display text-4xl font-black truncate">@{me.username}</h1>
          <div className="text-sm text-muted-foreground">{me.email}</div>
        </div>
      </header>

      <div className="grid md:grid-cols-4 gap-4">
        <Stat emoji="🐕" label="Total dogs" value={done.length} />
        <Stat emoji="⏳" label="In the queue" value={cooking.length} />
        <Stat emoji="✍️" label="Forum posts" value={myPosts.length} />
        <Stat
          emoji="👍/👎"
          label="Reactions received"
          value={`${likesReceived} / ${dislikesReceived}`}
        />
      </div>

      {cooking.length > 0 && (
        <div className="card-pop p-4 flex items-center gap-3 bg-sunshine/50">
          <span className="text-3xl animate-bounce">🐕</span>
          <div>
            <div className="font-display text-xl font-bold">
              {cooking.length} {cooking.length === 1 ? "dog" : "dogs"} still cooking
            </div>
            <div className="text-sm text-muted-foreground">
              They finish on their own — you'll get a notification for each one.
            </div>
          </div>
        </div>
      )}

      <section>
        <div className="flex flex-wrap items-end justify-between gap-3 mb-3">
          <h2 className="font-display text-3xl font-black">My dogs</h2>
          <Link to="/upload" className="btn-pop btn-pop-hover bg-card px-4 py-1.5 text-sm">
            + Upload more
          </Link>
        </div>

        <div className="flex gap-2 mb-4 flex-wrap">
          <Tab active={filter === "all"} onClick={() => setFilter("all")}>
            All ({jobs.length})
          </Tab>
          <Tab active={filter === "done"} onClick={() => setFilter("done")}>
            Done ({done.length})
          </Tab>
          <Tab active={filter === "cooking"} onClick={() => setFilter("cooking")}>
            In the queue ({cooking.length})
          </Tab>
        </div>

        {error && <div className="card-pop p-6 text-center text-destructive">{error}</div>}

        {!error && loading && jobs.length === 0 && (
          <div className="card-pop p-8 text-center text-muted-foreground">Loading your dogs…</div>
        )}

        {!error && !loading && visible.length === 0 ? (
          <div className="card-pop p-8 text-center text-muted-foreground">
            {jobs.length === 0 ? (
              <>
                No matches yet.{" "}
                <Link to="/upload" className="underline">
                  Upload one →
                </Link>
              </>
            ) : (
              <>Nothing in this bucket.</>
            )}
          </div>
        ) : (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {visible.map((job) => (
              <MyDog key={job.id} job={job} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function MyDog({ job }: { job: UploadJob }) {
  // Sharing is what puts a match in the public gallery. There used to be a
  // `shareMatch` action in the mock store that no page ever called, so nothing
  // could actually be shared — this is the button that was missing.
  //
  // `job.shared` is read straight from the feed rather than mirrored into local
  // state. A mirror initialised from a prop goes stale as soon as the page
  // unmounts and remounts, and a stale toggle doesn't just *look* wrong — it
  // sends the wrong request. This one shared twice instead of unsharing, so a
  // photo stayed public after the button claimed to have made it private.
  const { add, remove: dropFromFeed } = useUploadFeed();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState("");
  const shared = job.shared;

  async function remove(ev: React.MouseEvent) {
    ev.preventDefault();
    ev.stopPropagation();
    // Deleting the photo takes the forum post that shared it, because the post
    // *was* the photo — a caption pointing at nothing is worse than no post.
    if (
      !window.confirm(
        "Delete this photo? The files are erased, and any forum post that shared it goes too. This can't be undone.",
      )
    ) {
      return;
    }
    setBusy(true);
    setFailed("");
    try {
      await uploadApi.remove(job.id);
      dropFromFeed(job.id);
    } catch (err) {
      setFailed(err instanceof Error ? err.message : "Couldn't delete that.");
      setBusy(false);
    }
  }

  async function toggleShare(ev: React.MouseEvent) {
    ev.preventDefault(); // the whole card is a link to the result page
    ev.stopPropagation();
    setBusy(true);
    setFailed("");
    try {
      const updated = shared ? await uploadApi.unshare(job.id) : await uploadApi.share(job.id);
      add([updated]); // back into the feed, so every view agrees
    } catch (err) {
      setFailed(err instanceof Error ? err.message : "That didn't work.");
    } finally {
      setBusy(false);
    }
  }

  const body = (
    <div className="card-pop-sm p-3 h-full">
      <div className="flex items-center gap-2">
        <img
          src={uploadImageUrl(job.id)}
          alt={job.filename}
          className="h-20 w-20 rounded-xl border-2 border-[var(--ink)] object-cover shrink-0"
        />
        <span className="text-xl shrink-0" aria-hidden="true">
          →
        </span>
        {job.dog ? (
          <img
            src={job.dog.imageUrl}
            alt="the matched dog"
            className="h-20 w-20 rounded-xl border-2 border-[var(--ink)] object-cover shrink-0"
          />
        ) : (
          <div className="h-20 w-20 rounded-xl border-2 border-[var(--ink)] bg-muted grid place-items-center text-2xl shrink-0">
            {job.status === "error" ? "⚠️" : <span className="animate-pulse">🐾</span>}
          </div>
        )}
      </div>

      <div className="mt-2 flex items-center justify-between gap-2">
        <span className="text-xs font-bold truncate" title={job.filename}>
          {job.filename}
        </span>
        <span className="text-[10px] font-bold shrink-0">{STATUS_LABEL[job.status]}</span>
      </div>

      {job.status === "done" && job.score != null && (
        <div className="text-xs font-bold mt-1">{Math.round(job.score * 100)}% match</div>
      )}
      {job.status === "error" && job.error && (
        <div className="text-xs text-destructive mt-1">{job.error}</div>
      )}
      <SharedTraits traits={job.sharedTraits} />

      {job.status === "done" && job.dog && (
        <button
          onClick={toggleShare}
          disabled={busy}
          className={`btn-pop btn-pop-hover mt-2 w-full px-2 py-1 text-xs ${
            shared ? "bg-mint" : "bg-card"
          } disabled:opacity-60`}
        >
          {busy
            ? "…"
            : shared
              ? "🌍 Shared — click to make private"
              : "🔒 Private — share to gallery"}
        </button>
      )}

      <button
        onClick={remove}
        disabled={busy}
        className="btn-pop btn-pop-hover mt-2 w-full px-2 py-1 text-xs bg-card text-destructive disabled:opacity-60"
      >
        🗑 Delete photo
      </button>
      {failed && <div className="text-xs text-destructive mt-1">{failed}</div>}
    </div>
  );

  // Only a finished match has somewhere to go.
  return job.status === "done" ? <Link to={`/result/${job.id}`}>{body}</Link> : body;
}

function Tab({
  active,
  children,
  onClick,
}: {
  active: boolean;
  children: React.ReactNode;
  onClick: () => void;
}) {
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
