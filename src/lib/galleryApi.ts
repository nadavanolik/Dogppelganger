/**
 * REST client for `/api/gallery` — matches their owners chose to publish.
 *
 * The only anonymous API in the app: the landing page shows a featured strip to
 * visitors who don't have an account yet. Nothing appears here unless an owner
 * explicitly shared it, and unsharing removes it immediately.
 */
import { api } from "./api";
import type { DogRef, SharedTrait } from "./uploadApi";

const BASE = "/api/gallery";

export type GalleryItem = {
  jobId: number;
  /** No media token needed — a shared match is readable by anyone. */
  imageUrl: string;
  thumbUrl: string;
  owner: { id: number | null; username: string };
  dog: DogRef | null;
  dogIndex: number | null;
  score: number | null;
  sharedTraits: SharedTrait[];
  sharedAt: string | null;
};

export const galleryApi = {
  list: (limit = 24, offset = 0) =>
    api.get<{ total: number; items: GalleryItem[] }>(`${BASE}?limit=${limit}&offset=${offset}`),

  featured: (limit = 6) => api.get<GalleryItem[]>(`${BASE}/featured?limit=${limit}`),
};

export type Notification = {
  id: number;
  kind: string;
  text: string;
  href: string | null;
  read: boolean;
  createdAt: string | null;
};

/**
 * The bell's icon for a notification kind. Kinds come from the backend as a
 * bare string (`app/models.py`): "match", "reaction", "comment". Chat messages
 * are deliberately never notifications — they live in the envelope badge.
 */
export function notificationIcon(kind: string): string {
  if (kind === "match") return "🐕";
  if (kind === "comment") return "💬";
  return "❤️";
}

export const notificationApi = {
  list: (limit = 30) =>
    api.get<{ unread: number; items: Notification[] }>(`/api/notifications?limit=${limit}`),

  markAllRead: () => api.post<{ markedRead: number }>("/api/notifications/read"),
};
