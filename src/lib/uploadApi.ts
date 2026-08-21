/**
 * REST client for `/api/uploads` — upload a batch of photos and track their
 * place in the queue. See backend/app/uploads for how jobs are processed.
 *
 * Every call is authenticated by the shared helper in `api.ts`; the photo
 * belongs to whoever the token says is calling.
 */

import { api, withMediaToken } from "./api";

const BASE = "/api/uploads";

export type UploadStatus = "queued" | "processing" | "done" | "error";

/**
 * One trait the person and their dog are both unusually high on.
 *
 * `strength` is the weaker side's percentile (see `_trait_strength` in
 * backend/app/ml/matcher.py) — "both of them are at least this far up the
 * corpus on this trait". It is null on matches made before strengths were
 * recorded, which render as the label alone.
 */
export type SharedTrait = { label: string; strength: number | null };

/**
 * The dog a photo was matched to — a row of `dog_assets`, not a breed label.
 *
 * AFHQ carries no breed annotations, so the API stopped claiming them: what
 * comes back is the actual photo that was retrieved, plus how close it scored
 * and which attributes the two faces had in common. The URLs are absolute
 * paths nginx serves off the corpus volume (see backend/DATA_STORAGE.md §2.2).
 */
export type DogRef = {
  id: number;
  slug: string;
  index: number | null;
  width: number;
  height: number;
  thumbUrl: string; // 128px — grids and game tiles
  imageUrl: string; // 256px — the default
  fullUrl: string; // 512px — when the photo is the point of the page
};

export type UploadJob = {
  id: number;
  filename: string;
  urgent: boolean;
  status: UploadStatus;
  /** Of the stored, re-encoded image — the queue's shortest-job-first proxy. */
  byteSize: number | null;
  width: number | null;
  height: number | null;
  dog: DogRef | null;
  dogIndex: number | null;
  /** Similarity, 0..1. Not a classifier's confidence. */
  score: number | null;
  /** Published to the public gallery. Private is the default. */
  shared: boolean;
  sharedAt: string | null;
  sharedTraits: SharedTrait[];
  error: string | null;
  createdAt: string | null;
  finishedAt: string | null;
};

export type Rejected = { filename: string; reason: string };

export type UploadResponse = {
  created: UploadJob[];
  rejected: Rejected[];
};

/**
 * The uploaded human photo. Unlike dog photos, this goes through the API
 * rather than nginx: it's personal data, so every read is access-checked and
 * marked no-store.
 *
 * An `<img>` element cannot send an Authorization header, so a short-lived
 * media token rides in the query string instead. Pass `signed: false` for a
 * photo shared to the public gallery — that one is readable by anyone, and
 * leaving the token off keeps the URL stable and cacheable.
 */
export function uploadImageUrl(
  jobId: number,
  size: "display" | "thumb" = "display",
  signed = true,
): string {
  const url = `${BASE}/${jobId}/image?size=${size}`;
  return signed ? withMediaToken(url) : url;
}

export const uploadApi = {
  /** Send a batch at once; `urgent` is positional, one flag per file. */
  upload(items: { file: File; urgent: boolean }[]): Promise<UploadResponse> {
    const form = new FormData();
    form.append("urgent", JSON.stringify(items.map((i) => i.urgent)));
    for (const { file } of items) form.append("files", file);
    return api.form<UploadResponse>(BASE, form);
  },

  /** One job — what the result page polls/subscribes for. */
  get(jobId: number): Promise<UploadJob> {
    return api.get<UploadJob>(`${BASE}/${jobId}`);
  },

  list(): Promise<UploadJob[]> {
    return api.get<UploadJob[]>(BASE);
  },

  /** Publish a finished match to the public gallery. */
  share(jobId: number): Promise<UploadJob> {
    return api.post<UploadJob>(`${BASE}/${jobId}/share`);
  },

  /** Take it back out. Private again on the very next request. */
  unshare(jobId: number): Promise<UploadJob> {
    return api.del<UploadJob>(`${BASE}/${jobId}/share`);
  },

  /** Delete the photo, its derivatives, and any post that shared it. */
  remove(jobId: number): Promise<void> {
    return api.del<void>(`${BASE}/${jobId}`);
  },
};
