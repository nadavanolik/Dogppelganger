/**
 * One live view of the signed-in owner's uploads, shared by the whole app.
 *
 * Every page that cares about matches — the upload queue, My dogs, a single
 * result — reads from here rather than fetching and subscribing for itself.
 * That matters for two reasons:
 *
 * 1. **One socket.** Every live feature shares the single connection in
 *    `appSocket.tsx`, so a browser holds one socket rather than one per
 *    page, each reconnecting independently.
 * 2. **Notifications arrive wherever you are.** The socket used to be mounted
 *    inside the upload page, so a dog that finished while you were reading the
 *    forum announced itself to nobody. Mounted at the shell, a finished match
 *    always reaches the bell.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";

import { useAuth } from "./auth";
import { useSocketEvent } from "./appSocket";
import { uploadApi, type UploadJob } from "./uploadApi";

type Feed = {
  jobs: UploadJob[];
  loading: boolean;
  error: string | null;
  /** Merge new *or updated* jobs in by id, so pages never hold a private copy. */
  add: (jobs: UploadJob[]) => void;
  /** Drop a deleted job. */
  remove: (jobId: number) => void;
};

const FeedCtx = createContext<Feed | null>(null);

function upsert(jobs: UploadJob[], incoming: UploadJob[]): UploadJob[] {
  const byId = new Map(jobs.map((j) => [j.id, j]));
  for (const job of incoming) byId.set(job.id, job);
  // Newest first, matching what the API returns.
  return [...byId.values()].sort((a, b) => b.id - a.id);
}

export function UploadFeedProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const ownerId = user?.id ?? null;

  const [jobs, setJobs] = useState<UploadJob[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Which jobs we've already announced. Without this, any re-render that
  // replayed a "done" job would ring the bell again.
  const announced = useRef<Set<number>>(new Set());

  useEffect(() => {
    announced.current = new Set();
    setJobs([]);
    if (!ownerId) return;

    let cancelled = false;
    setLoading(true);
    uploadApi
      .list()
      .then((rows) => {
        if (cancelled) return;
        // Everything already finished is history, not news — seed the set so
        // signing in doesn't announce every dog you have ever made.
        for (const row of rows) if (row.status === "done") announced.current.add(row.id);
        setJobs(rows);
        setError(null);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Couldn't load your dogs.");
      })
      .finally(() => !cancelled && setLoading(false));

    return () => {
      cancelled = true;
    };
  }, [ownerId]);

  // Arrives on the one app-wide socket, so a dog that finishes while you're
  // reading the forum still reaches the bell.
  useSocketEvent("upload_update", (event) => {
    const job = event.payload as unknown as UploadJob;
    if (!job?.id) return;
    setJobs((prev) => upsert(prev, [job]));
    if (job.status === "done" && !announced.current.has(job.id)) {
      announced.current.add(job.id);
    }
  });

  const add = useCallback((incoming: UploadJob[]) => {
    // Upserts by id, so this is also how a page writes a *changed* job back —
    // sharing, for instance. A component that keeps its own copy of a job's
    // state instead will go stale the moment the page unmounts, and then act on
    // the stale value: that is exactly how the share toggle briefly became a
    // button that could only ever share, never unshare.
    setJobs((prev) => upsert(prev, incoming));
  }, []);

  const remove = useCallback((jobId: number) => {
    setJobs((prev) => prev.filter((j) => j.id !== jobId));
  }, []);

  const value = useMemo<Feed>(
    () => ({ jobs, loading, error, add, remove }),
    [jobs, loading, error, add, remove],
  );

  return <FeedCtx.Provider value={value}>{children}</FeedCtx.Provider>;
}

export function useUploadFeed(): Feed {
  const ctx = useContext(FeedCtx);
  if (!ctx) throw new Error("useUploadFeed must be used inside <UploadFeedProvider>");
  return ctx;
}

/** One job by id, or null while it loads / if it isn't yours. */
export function useUploadJob(jobId: number): UploadJob | null {
  const { jobs } = useUploadFeed();
  return jobs.find((j) => j.id === jobId) ?? null;
}
