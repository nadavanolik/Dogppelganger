/**
 * One live view of the signed-in owner's uploads, shared by the whole app.
 *
 * Every page that cares about matches — the upload queue, My dogs, a single
 * result — reads from here rather than fetching and subscribing for itself.
 * That matters for two reasons:
 *
 * 1. **One socket.** Each `useUploadNotifications` call opens its own
 *    connection, so a per-page subscription meant two or three sockets for one
 *    browser, each reconnecting independently.
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

import { useStore } from "./store";
import { uploadApi, type UploadJob } from "./uploadApi";
import { useUploadNotifications } from "./uploadSocket";

type Feed = {
  jobs: UploadJob[];
  loading: boolean;
  error: string | null;
  /** Merge freshly-created jobs in, so the page doesn't wait for a refetch. */
  add: (jobs: UploadJob[]) => void;
};

const FeedCtx = createContext<Feed | null>(null);

function upsert(jobs: UploadJob[], incoming: UploadJob[]): UploadJob[] {
  const byId = new Map(jobs.map((j) => [j.id, j]));
  for (const job of incoming) byId.set(job.id, job);
  // Newest first, matching what the API returns.
  return [...byId.values()].sort((a, b) => b.id - a.id);
}

export function UploadFeedProvider({ children }: { children: ReactNode }) {
  const { state, notifyMatchReady } = useStore();
  const ownerId = state.user?.id ?? null;

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
      .list(ownerId)
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

  useUploadNotifications(ownerId, (job) => {
    setJobs((prev) => upsert(prev, [job]));
    if (job.status === "done" && !announced.current.has(job.id)) {
      announced.current.add(job.id);
      notifyMatchReady(job.id, job.filename);
    }
  });

  const add = useCallback((incoming: UploadJob[]) => {
    // Jobs land here queued, so they are not announced yet — the socket will
    // do that when each one finishes.
    setJobs((prev) => upsert(prev, incoming));
  }, []);

  const value = useMemo<Feed>(() => ({ jobs, loading, error, add }), [jobs, loading, error, add]);

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
