/**
 * REST client for `/api/uploads` — upload a batch of photos and track their
 * place in the queue. See backend/app/uploads for how jobs are processed.
 *
 * Identity here is the same seam as gameApi/gameSocket: an `ownerId` string
 * from the local-only mock auth, not a real login token.
 */

const BASE = "/api/uploads";

export type UploadStatus = "queued" | "processing" | "done" | "error";

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
  sharedTraits: string[];
  error: string | null;
  createdAt: string | null;
  finishedAt: string | null;
};

export type Rejected = { filename: string; reason: string };

export type UploadResponse = {
  created: UploadJob[];
  rejected: Rejected[];
};

export class UploadApiError extends Error {}

/**
 * The uploaded human photo. Unlike dog photos, this goes through the API
 * rather than nginx: it's personal data, so every read is ownership-checked
 * and marked no-store.
 */
export function uploadImageUrl(
  ownerId: string,
  jobId: number,
  size: "display" | "thumb" = "display",
): string {
  return `${BASE}/${jobId}/image?ownerId=${encodeURIComponent(ownerId)}&size=${size}`;
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail = body?.detail;
    throw new UploadApiError(
      typeof detail === "string" ? detail : `Request failed (${res.status}).`,
    );
  }
  return res.json() as Promise<T>;
}

export const uploadApi = {
  /** Send a batch at once; `urgent` is positional, one flag per file. */
  async upload(ownerId: string, items: { file: File; urgent: boolean }[]): Promise<UploadResponse> {
    const form = new FormData();
    form.append("ownerId", ownerId);
    form.append("urgent", JSON.stringify(items.map((i) => i.urgent)));
    for (const { file } of items) form.append("files", file);

    let res: Response;
    try {
      res = await fetch(BASE, { method: "POST", body: form });
    } catch {
      throw new UploadApiError("Can't reach the server. Is the backend running?");
    }
    return handle<UploadResponse>(res);
  },

  async list(ownerId: string): Promise<UploadJob[]> {
    let res: Response;
    try {
      res = await fetch(`${BASE}?ownerId=${encodeURIComponent(ownerId)}`);
    } catch {
      throw new UploadApiError("Can't reach the server. Is the backend running?");
    }
    return handle<UploadJob[]>(res);
  },
};
