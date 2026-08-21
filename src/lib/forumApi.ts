/**
 * REST client for `/api/forum` — sharing a finished dog photo with a
 * caption, likes/dislikes, and comments. See backend/app/forum.
 *
 * Every call is authenticated by the shared helper in `api.ts` — the author
 * of a post or a reaction is whoever holds the token, not a name in the body.
 */
import { api } from "./api";
import type { DogRef, SharedTrait, UploadJob } from "./uploadApi";

export { ApiError } from "./api";

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
  authorId: number | null;
  authorName: string;
  body: string;
  image: PostImage | null;
  createdAt: string | null;
  commentCount: number;
};

export type ForumComment = ReactionSummary & {
  id: number;
  postId: number;
  authorId: number | null;
  authorName: string;
  body: string;
  createdAt: string | null;
};

export type PostWithComments = ForumPost & { comments: ForumComment[] };

export const forumApi = {
  list: () => api.get<ForumPost[]>(BASE),

  get: (id: number) => api.get<PostWithComments>(`${BASE}/${id}`),

  create: (body: string, imageJobId?: number | null) =>
    api.post<ForumPost>(BASE, { body, imageJobId: imageJobId ?? null }),

  comment: (postId: number, body: string) =>
    api.post<ForumComment>(`${BASE}/${postId}/comments`, { body }),

  react: (targetType: "post" | "comment", targetId: number, kind: ReactionKind) =>
    api.post<ReactionSummary>(`${BASE}/react`, { targetType, targetId, kind }),

  /** Delete your own post, with its comments and reactions. Keeps the photo. */
  removePost: (postId: number) => api.del<void>(`${BASE}/${postId}`),

  /** Delete your own comment. */
  removeComment: (commentId: number) => api.del<void>(`${BASE}/comments/${commentId}`),

  /** My finished dogs that aren't already backing a post. */
  shareable: () => api.get<UploadJob[]>(`${BASE}/shareable`),

  byAuthor: (authorId: number) => api.get<ForumPost[]>(`${BASE}?authorId=${authorId}`),
};
