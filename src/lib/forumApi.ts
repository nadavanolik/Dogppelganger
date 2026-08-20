/**
 * REST client for `/api/forum` — sharing a finished dog photo with a
 * caption, likes/dislikes, and comments. See backend/app/forum.
 *
 * Identity here is the same seam as gameApi/uploadApi: an id/name pair from
 * the local-only mock auth, not a real login token.
 */
import type { DogRef, SharedTrait, UploadJob } from "./uploadApi";

const BASE = "/api/forum";

export type ReactionKind = "like" | "dislike";

export type ReactionSummary = {
  likeCount: number;
  dislikeCount: number;
  myReaction: ReactionKind | null;
};

/** The shared match behind a post: the author's upload plus the dog it drew. */
export type PostImage = {
  jobId: number;
  dog: DogRef | null;
  dogIndex: number | null;
  score: number | null;
  sharedTraits: SharedTrait[];
};

export type ForumPost = ReactionSummary & {
  id: number;
  authorId: string;
  authorName: string;
  body: string;
  image: PostImage | null;
  createdAt: string | null;
  commentCount: number;
};

export type ForumComment = ReactionSummary & {
  id: number;
  postId: number;
  authorId: string;
  authorName: string;
  body: string;
  createdAt: string | null;
};

export type PostWithComments = ForumPost & { comments: ForumComment[] };

export class ForumApiError extends Error {}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail = body?.detail;
    throw new ForumApiError(
      typeof detail === "string" ? detail : `Request failed (${res.status}).`,
    );
  }
  return res.json() as Promise<T>;
}

async function getJson<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`);
  } catch {
    throw new ForumApiError("Can't reach the server. Is the backend running?");
  }
  return handle<T>(res);
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ForumApiError("Can't reach the server. Is the backend running?");
  }
  return handle<T>(res);
}

export const forumApi = {
  list: (viewerId: string) => getJson<ForumPost[]>(`?viewerId=${encodeURIComponent(viewerId)}`),

  get: (id: number, viewerId: string) =>
    getJson<PostWithComments>(`/${id}?viewerId=${encodeURIComponent(viewerId)}`),

  create: (authorId: string, authorName: string, body: string, imageJobId?: number | null) =>
    postJson<ForumPost>("", { authorId, authorName, body, imageJobId: imageJobId ?? null }),

  comment: (postId: number, authorId: string, authorName: string, body: string) =>
    postJson<ForumComment>(`/${postId}/comments`, { authorId, authorName, body }),

  react: (userId: string, targetType: "post" | "comment", targetId: number, kind: ReactionKind) =>
    postJson<ReactionSummary>("/react", { userId, targetType, targetId, kind }),

  /** The owner's finished dogs that aren't already backing a post. */
  shareable: (ownerId: string) =>
    getJson<UploadJob[]>(`/shareable?ownerId=${encodeURIComponent(ownerId)}`),
};
