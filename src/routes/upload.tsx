import { useNavigate } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import { AppShell, RequireAuth } from "@/components/AppShell";
import { SharedTraits } from "@/components/MatchPair";
import { useStore } from "@/lib/store";
import { uploadApi, uploadImageUrl, type Rejected, type UploadJob } from "@/lib/uploadApi";
import { useUploadNotifications } from "@/lib/uploadSocket";

export default UploadPage;

function UploadPage() {
  return (
    <AppShell>
      <RequireAuth>
        <Upload />
      </RequireAuth>
    </AppShell>
  );
}

// The browser's <input accept> is only a filter suggestion — a user can still
// pick "All files", so this is checked again for real (bytes, not just this
// header) on the server before anything is queued.
const ACCEPTED_TYPES = new Set(["image/png", "image/jpeg"]);

type PendingImage = { file: File; src: string; urgent: boolean };

function Upload() {
  const { state, submitMatch } = useStore();
  const navigate = useNavigate();
  const owner = state.user ?? state.users[0];
  const [mode, setMode] = useState<"single" | "multi">("single");
  const [urgent, setUrgent] = useState(false);
  const single = useRef<HTMLInputElement>(null);

  // --------------------------------------------------------- multi / queue
  const [pending, setPending] = useState<PendingImage[]>([]);
  const [rejected, setRejected] = useState<Rejected[]>([]);
  const [jobs, setJobs] = useState<UploadJob[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    uploadApi
      .list(owner.id)
      .then((rows) => {
        if (!cancelled) setJobs(rows);
      })
      .catch((err) => {
        if (!cancelled)
          setLoadError(err instanceof Error ? err.message : "Couldn't load your queue.");
      });
    return () => {
      cancelled = true;
    };
  }, [owner.id]);

  useUploadNotifications(owner.id, (job) => {
    setJobs((prev) => {
      const exists = prev.some((j) => j.id === job.id);
      return exists ? prev.map((j) => (j.id === job.id ? job : j)) : [job, ...prev];
    });
  });

  async function readFile(f: File) {
    return new Promise<string>((res) => {
      const r = new FileReader();
      r.onload = () => res(r.result as string);
      r.readAsDataURL(f);
    });
  }

  async function onSingle(files: FileList | null) {
    if (!files || !files[0]) return;
    const src = await readFile(files[0]);
    const m = submitMatch(src, urgent);
    navigate(`/result/${m.id}`);
  }

  async function onMulti(files: FileList | null) {
    if (!files) return;
    const accepted: PendingImage[] = [];
    const badFiles: Rejected[] = [];
    for (const f of Array.from(files)) {
      if (!ACCEPTED_TYPES.has(f.type)) {
        badFiles.push({
          filename: f.name,
          reason: "not a valid image file — only PNG and JPG are accepted",
        });
        continue;
      }
      accepted.push({ file: f, src: await readFile(f), urgent: false });
    }
    setPending((p) => [...p, ...accepted]);
    if (badFiles.length > 0) setRejected((r) => [...badFiles, ...r]);
  }

  async function submitQueue() {
    if (pending.length === 0 || submitting) return;
    setSubmitting(true);
    try {
      const res = await uploadApi.upload(
        owner.id,
        pending.map((p) => ({ file: p.file, urgent: p.urgent })),
      );
      setJobs((prev) => [...res.created, ...prev]);
      if (res.rejected.length > 0) setRejected((r) => [...res.rejected, ...r]);
      setPending([]);
    } catch (err) {
      setRejected((r) => [
        { filename: "", reason: err instanceof Error ? err.message : "Upload failed." },
        ...r,
      ]);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="grid md:grid-cols-3 gap-6">
      <div className="md:col-span-2 card-pop p-6">
        <h1 className="font-display text-4xl font-black">Get dogified</h1>
        <p className="text-muted-foreground mt-1">
          Prototype note: your photo stays local. Matching is playful and instant (or queued when in
          multi mode).
        </p>

        <div className="mt-5 flex gap-2">
          <TabBtn active={mode === "single"} onClick={() => setMode("single")}>
            Single upload
          </TabBtn>
          <TabBtn active={mode === "multi"} onClick={() => setMode("multi")}>
            Multi upload · priority queue
          </TabBtn>
        </div>

        {mode === "single" ? (
          <div className="mt-6">
            <label className="flex items-center gap-2 mb-4">
              <input
                type="checkbox"
                checked={urgent}
                onChange={(e) => setUrgent(e.target.checked)}
                className="h-5 w-5 accent-[var(--primary)]"
              />
              <span className="font-bold">🚨 Mark this one urgent</span>
            </label>
            <div
              onClick={() => single.current?.click()}
              className="cursor-pointer border-4 border-dashed border-[var(--ink)] rounded-3xl p-10 text-center bg-sunshine/40 hover:bg-sunshine transition"
            >
              <div className="text-6xl">📸</div>
              <div className="mt-2 font-display text-2xl font-bold">Drop a face here</div>
              <div className="text-muted-foreground">or click to upload a png/jpg</div>
              <input
                ref={single}
                type="file"
                accept="image/png,image/jpeg"
                className="hidden"
                onChange={(e) => onSingle(e.target.files)}
              />
            </div>
          </div>
        ) : (
          <div className="mt-6">
            <label className="block border-4 border-dashed border-[var(--ink)] rounded-3xl p-8 text-center bg-bubblegum/40 hover:bg-bubblegum cursor-pointer">
              <div className="text-5xl">🗂️</div>
              <div className="font-display text-xl font-bold mt-1">Drop many images at once</div>
              <div className="text-muted-foreground text-sm">
                Each becomes its own queued job. Mark any as urgent below.
              </div>
              <input
                type="file"
                accept="image/png,image/jpeg"
                multiple
                className="hidden"
                onChange={(e) => {
                  onMulti(e.target.files);
                  e.target.value = "";
                }}
              />
            </label>

            {rejected.length > 0 && (
              <div className="mt-4 space-y-1">
                {rejected.map((r, i) => (
                  <div
                    key={i}
                    className="p-2 rounded-xl bg-destructive/10 border-2 border-destructive text-destructive text-sm flex justify-between gap-2"
                  >
                    <span>
                      {r.filename ? <b>{r.filename}</b> : null} {r.reason}
                    </span>
                    <button
                      onClick={() => setRejected((r2) => r2.filter((_, j) => j !== i))}
                      className="font-bold shrink-0"
                      aria-label="Dismiss"
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            )}

            {pending.length > 0 && (
              <div className="mt-5">
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                  {pending.map((p, i) => (
                    <div key={i} className="card-pop-sm p-2">
                      <img
                        src={p.src}
                        className="w-full aspect-square object-cover rounded-lg border-2 border-[var(--ink)]"
                        alt=""
                      />
                      <div className="mt-2 flex items-center justify-between gap-1">
                        <label className="flex items-center gap-1 text-xs font-bold">
                          <input
                            type="checkbox"
                            checked={p.urgent}
                            onChange={(e) =>
                              setPending((prev) =>
                                prev.map((x, j) =>
                                  j === i ? { ...x, urgent: e.target.checked } : x,
                                ),
                              )
                            }
                            className="accent-[var(--primary)]"
                          />
                          🚨 urgent
                        </label>
                        <button
                          onClick={() => setPending((prev) => prev.filter((_, j) => j !== i))}
                          className="text-xs text-muted-foreground hover:text-destructive"
                          aria-label="Remove"
                        >
                          ✕
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
                <button
                  onClick={submitQueue}
                  disabled={submitting}
                  className="btn-pop btn-pop-hover bg-primary text-primary-foreground mt-4 px-5 py-3 text-lg disabled:opacity-60"
                >
                  {submitting ? "Sending…" : `Send ${pending.length} to the queue`}
                </button>
              </div>
            )}

            <UploadQueue ownerId={owner.id} jobs={jobs} loadError={loadError} />
          </div>
        )}
      </div>

      <aside className="card-pop p-5 h-fit">
        <div className="font-display text-xl font-black">How it works</div>
        <ol className="mt-3 space-y-3 text-sm">
          <li className="flex gap-2">
            <span>1️⃣</span>
            <span>Upload a face (or many).</span>
          </li>
          <li className="flex gap-2">
            <span>2️⃣</span>
            <span>Our very serious dogify engine assigns a breed.</span>
          </li>
          <li className="flex gap-2">
            <span>3️⃣</span>
            <span>Urgent images jump the queue.</span>
          </li>
          <li className="flex gap-2">
            <span>4️⃣</span>
            <span>
              Watch progress live in <b>My Dogs</b>.
            </span>
          </li>
        </ol>
        <div className="mt-4 p-3 rounded-xl bg-mint border-2 border-[var(--ink)] text-sm">
          Multi-upload runs in the background so you can browse the forum while dogs cook.
        </div>
      </aside>
    </div>
  );
}

const STATUS_LABEL: Record<UploadJob["status"], string> = {
  queued: "⏳ queued",
  processing: "🐾 processing",
  done: "✅ done",
  error: "⚠️ error",
};

const STATUS_CLASS: Record<UploadJob["status"], string> = {
  queued: "bg-sky text-sky-foreground",
  processing: "bg-sunshine text-sunshine-foreground animate-pulse",
  done: "bg-mint text-mint-foreground",
  error: "bg-destructive text-destructive-foreground",
};

function UploadQueue({
  ownerId,
  jobs,
  loadError,
}: {
  ownerId: string;
  jobs: UploadJob[];
  loadError: string | null;
}) {
  if (loadError) {
    return <div className="mt-6 text-sm text-destructive">{loadError}</div>;
  }
  if (jobs.length === 0) return null;

  return (
    <div className="mt-8">
      <div className="font-display text-xl font-bold mb-3">Your queue</div>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {jobs.map((job) => (
          <div key={job.id} className="card-pop-sm p-2">
            <div className="relative">
              <img
                src={uploadImageUrl(ownerId, job.id)}
                className="w-full aspect-square object-cover rounded-lg border-2 border-[var(--ink)]"
                alt={job.filename}
              />
              {job.urgent && (
                <span className="absolute top-1 left-1 text-lg" title="Urgent">
                  🚨
                </span>
              )}
            </div>
            <div className="mt-2 flex items-center justify-between gap-1">
              <span className="text-xs font-bold truncate" title={job.filename}>
                {job.filename}
              </span>
              <span
                className={`text-[10px] font-bold px-2 py-0.5 rounded-full border border-[var(--ink)] shrink-0 ${STATUS_CLASS[job.status]}`}
              >
                {STATUS_LABEL[job.status]}
              </span>
            </div>
            {job.status === "done" && job.dog && (
              <div className="mt-2 flex items-center gap-2">
                <img
                  src={job.dog.thumbUrl}
                  alt="the matched dog"
                  className="h-10 w-10 object-cover rounded-lg border-2 border-[var(--ink)] shrink-0"
                />
                {job.score != null && (
                  <div className="text-xs font-bold">{Math.round(job.score * 100)}% match</div>
                )}
              </div>
            )}
            {job.status === "done" && <SharedTraits traits={job.sharedTraits} />}
            {job.status === "error" && job.error && (
              <div className="mt-1 text-xs text-destructive">{job.error}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function TabBtn({
  active,
  ...p
}: { active: boolean } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...p}
      className={`btn-pop btn-pop-hover px-4 py-2 text-sm ${active ? "bg-primary text-primary-foreground" : "bg-card"}`}
    />
  );
}
