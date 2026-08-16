/**
 * REST client for `/api/uploads` — upload a batch of photos and track their
 * place in the queue. See backend/app/uploads for how jobs are processed.
 *
 * Identity here is the same seam as gameApi/gameSocket: an `ownerId` string
 * from the local-only mock auth, not a real login token.
 */

const BASE = "/api/uploads";

export type UploadStatus = "queued" | "processing" | "done" | "error";

export type UploadJob = {
  id: number;
  filename: string;
  urgent: boolean;
  status: UploadStatus;
  breedName: string | null;
  trait: string | null;
  confidence: number | null;
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

export function uploadImageUrl(ownerId: string, jobId: number): string {
  return `${BASE}/${jobId}/image?ownerId=${encodeURIComponent(ownerId)}`;
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
