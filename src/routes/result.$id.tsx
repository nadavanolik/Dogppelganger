import { Link, useNavigate, useParams } from "react-router-dom";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { SharedTraits } from "@/components/MatchPair";
import { useAuth } from "@/lib/auth";
import { uploadApi, uploadImageUrl, type UploadJob } from "@/lib/uploadApi";
import { useUploadJob } from "@/lib/uploadFeed";

export default ResultPage;

function ResultPage() {
  return (
    <AppShell>
      <div className="max-w-3xl mx-auto mb-4">
        <Link to="/profile" className="text-sm underline">
          ← back to profile
        </Link>
      </div>
      <Result />
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
  const { user } = useAuth();
  const navigate = useNavigate();
  const owner = user!;

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
      .get(jobId)
      .then((row) => !cancelled && setJob(row))
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : "Not found."));
    return () => {
      cancelled = true;
    };
  }, [owner.id, jobId]);

  // The shared feed carries live updates for every job, so a page opened while
  // the dog is still cooking resolves on its own. It also wins over our own
  // fetch, which is only there for a deep link that arrives first.
  const live = useUploadJob(jobId);
  const shown = live ?? job;

  if (error) {
    return <div className="card-pop p-8 text-center">{error}</div>;
  }
  if (!shown) {
    return <div className="card-pop p-8 text-center text-muted-foreground">Loading…</div>;
  }

  if (shown.status === "error") {
    return (
      <div className="max-w-3xl mx-auto card-pop p-8 text-center">
        <div className="text-6xl">😞</div>
        <h1 className="font-display text-3xl font-black mt-3">That one didn't work</h1>
        <p className="text-muted-foreground mt-2">{shown.error}</p>
        <Link
          to="/upload"
          className="btn-pop btn-pop-hover bg-primary text-primary-foreground inline-block mt-6 px-5 py-2"
        >
          Try another
        </Link>
      </div>
    );
  }

  if (shown.status !== "done" || !shown.dog) {
    return (
      <div className="max-w-3xl mx-auto card-pop p-8 text-center py-12">
        <div className="text-7xl animate-bounce">🐕</div>
        <div className="mt-4 font-display text-3xl font-black">
          {shown.status === "queued" ? "In the queue…" : "Finding your dog…"}
        </div>
        <p className="text-muted-foreground mt-1">
          {shown.urgent ? "🚨 Urgent priority — coming right up." : "This page updates on its own."}
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto card-pop p-8">
      <div className="text-center">
        <div className="text-sm font-bold text-muted-foreground uppercase tracking-wide">
          Your dogppelganger is…
        </div>
        {shown.score != null && (
          <h1 className="font-display text-5xl md:text-6xl font-black mt-1">
            {Math.round(shown.score * 100)}% match
          </h1>
        )}
      </div>

      <div className="mt-8 flex items-center justify-center gap-6">
        <img
          src={uploadImageUrl(shown.id)}
          alt="your photo"
          className="h-36 w-36 rounded-2xl border-2 border-[var(--ink)] object-cover"
        />
        <div className="text-5xl" aria-hidden="true">
          →
        </div>
        <img
          src={shown.dog.fullUrl}
          alt="the dog you matched"
          className="h-36 w-36 rounded-2xl border-2 border-[var(--ink)] object-cover"
        />
      </div>

      <div className="mt-8 flex justify-center">
        <div className="max-w-sm">
          <SharedTraits traits={shown.sharedTraits} />
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
          href={shown.dog.fullUrl}
          download={`${shown.dog.slug}.jpg`}
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
