import { Link, useNavigate, useParams } from "react-router-dom";
import { useEffect, useState } from "react";
import { AppShell, RequireAuth } from "@/components/AppShell";
import { SharedTraits } from "@/components/MatchPair";
import { useStore } from "@/lib/store";
import { uploadApi, uploadImageUrl, type UploadJob } from "@/lib/uploadApi";
import { useUploadNotifications } from "@/lib/uploadSocket";

export default ResultPage;

function ResultPage() {
  return (
    <AppShell>
      <RequireAuth>
        <Result />
      </RequireAuth>
    </AppShell>
  );
}

/**
 * One finished match, in full.
 *
 * Reads the real job from `/api/uploads/:id`. It used to read the localStorage
 * mock, which captioned every match with a breed picked by
 * `randomBreed(humanImg + Date.now())` — a name drawn independently of the
 * photo beside it, so a Yorkshire terrier was captioned "Corgi" and a reload
 * gave a different answer. AFHQ carries no breed labels, so there was never a
 * real name to show. What the model actually knows is which dog it retrieved
 * and which traits the two share, and that is what this page says now.
 */
function Result() {
  const { id } = useParams();
  const { state } = useStore();
  const navigate = useNavigate();
  const owner = state.user ?? state.users[0];

  const jobId = Number(id);
  const [job, setJob] = useState<UploadJob | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!Number.isFinite(jobId)) {
      setError("That isn't a match id.");
      return;
    }
    let cancelled = false;
    uploadApi
      .get(owner.id, jobId)
      .then((row) => !cancelled && setJob(row))
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : "Not found."));
    return () => {
      cancelled = true;
    };
  }, [owner.id, jobId]);

  // Still queued when the page opened? The socket finishes the job for us, so
  // the page resolves on its own instead of asking the user to refresh.
  useUploadNotifications(owner.id, (incoming) => {
    if (incoming.id === jobId) setJob(incoming);
  });

  if (error) {
    return <div className="card-pop p-8 text-center">{error}</div>;
  }
  if (!job) {
    return <div className="card-pop p-8 text-center text-muted-foreground">Loading…</div>;
  }

  if (job.status === "error") {
    return (
      <div className="max-w-3xl mx-auto card-pop p-8 text-center">
        <div className="text-6xl">😞</div>
        <h1 className="font-display text-3xl font-black mt-3">That one didn't work</h1>
        <p className="text-muted-foreground mt-2">{job.error}</p>
        <Link
          to="/upload"
          className="btn-pop btn-pop-hover bg-primary text-primary-foreground inline-block mt-6 px-5 py-2"
        >
          Try another
        </Link>
      </div>
    );
  }

  if (job.status !== "done" || !job.dog) {
    return (
      <div className="max-w-3xl mx-auto card-pop p-8 text-center py-12">
        <div className="text-7xl animate-bounce">🐕</div>
        <div className="mt-4 font-display text-3xl font-black">
          {job.status === "queued" ? "In the queue…" : "Finding your dog…"}
        </div>
        <p className="text-muted-foreground mt-1">
          {job.urgent ? "🚨 Urgent priority — coming right up." : "This page updates on its own."}
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto card-pop p-8">
      <div className="text-center">
        <div className="text-sm font-bold text-muted-foreground uppercase tracking-wide">
          Your dogppleganger is…
        </div>
        {job.score != null && (
          <h1 className="font-display text-5xl md:text-6xl font-black mt-1">
            {Math.round(job.score * 100)}% match
          </h1>
        )}
      </div>

      <div className="mt-8 flex items-center justify-center gap-6">
        <img
          src={uploadImageUrl(owner.id, job.id)}
          alt="your photo"
          className="h-36 w-36 rounded-2xl border-2 border-[var(--ink)] object-cover"
        />
        <div className="text-5xl" aria-hidden="true">
          →
        </div>
        <img
          src={job.dog.fullUrl}
          alt="the dog you matched"
          className="h-36 w-36 rounded-2xl border-2 border-[var(--ink)] object-cover"
        />
      </div>

      <div className="mt-8 flex justify-center">
        <div className="max-w-sm">
          <SharedTraits traits={job.sharedTraits} />
        </div>
      </div>

      <div className="mt-8 flex flex-wrap gap-3 justify-center">
        <Link
          to="/forum/new"
          className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-5 py-2"
        >
          📣 Share to the forum
        </Link>
        <a
          href={job.dog.fullUrl}
          download={`${job.dog.slug}.jpg`}
          className="btn-pop btn-pop-hover bg-card px-5 py-2"
        >
          ⬇️ Download the dog
        </a>
        <button
          onClick={() => navigate("/upload")}
          className="btn-pop btn-pop-hover bg-sunshine px-5 py-2"
        >
          🔁 Try another
        </button>
      </div>
    </div>
  );
}
