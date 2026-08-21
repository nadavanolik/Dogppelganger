import { Link, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";

import { forumApi, ApiError } from "@/lib/forumApi";
import { uploadImageUrl, type UploadJob } from "@/lib/uploadApi";

export default NewPost;

function NewPost() {
  return (
    <AppShell>
      <Inner />
    </AppShell>
  );
}

function Inner() {
  const navigate = useNavigate();
  const [body, setBody] = useState("");
  const [shareable, setShareable] = useState<UploadJob[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    forumApi
      .shareable()
      .then((rows) => {
        if (!cancelled) setShareable(rows);
      })
      .catch((err) => {
        if (!cancelled)
          setLoadError(err instanceof Error ? err.message : "Couldn't load your finished dogs.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function publish() {
    if (!body.trim() || submitting) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const post = await forumApi.create(body.trim(), selected);
      navigate(`/forum/${post.id}`);
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : "Couldn't publish that post.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto card-pop p-6">
      <h1 className="font-display text-3xl font-black">New post</h1>
      <div className="mt-4 space-y-3">
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="Say your piece — or write a caption for a dog you're sharing"
          rows={6}
          className="w-full rounded-xl border-2 border-[var(--ink)] px-3 py-2 bg-card"
        />

        <div>
          <div className="text-sm font-bold text-muted-foreground mb-2">
            Share one of your finished dogs? (optional)
          </div>
          {loadError && <div className="text-sm text-destructive">{loadError}</div>}
          {!loadError && shareable.length === 0 && (
            <div className="text-sm text-muted-foreground">
              No unshared finished dogs yet — upload some in{" "}
              <Link to="/upload" className="underline">
                Match
              </Link>
              .
            </div>
          )}
          {shareable.length > 0 && (
            <div className="grid grid-cols-3 sm:grid-cols-4 gap-3">
              {shareable.map((job) => (
                <button
                  key={job.id}
                  type="button"
                  onClick={() => setSelected((s) => (s === job.id ? null : job.id))}
                  className={`card-pop-sm p-2 text-left ${selected === job.id ? "ring-4 ring-[var(--primary)]" : ""}`}
                >
                  <img
                    src={uploadImageUrl(job.id, "thumb")}
                    className="w-full aspect-square object-cover rounded-lg border-2 border-[var(--ink)]"
                    alt={job.filename}
                  />
                  <div className="mt-1 text-xs font-bold truncate">
                    {job.score != null ? `${Math.round(job.score * 100)}% match` : job.filename}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {submitError && <div className="text-sm text-destructive">{submitError}</div>}

        <div className="flex justify-end gap-2">
          <button
            disabled={!body.trim() || submitting}
            onClick={publish}
            className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-5 py-2 disabled:opacity-50"
          >
            {submitting ? "Publishing…" : "Publish"}
          </button>
        </div>
      </div>
    </div>
  );
}
