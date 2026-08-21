/**
 * REST client for `/api/dm` — private 1:1 conversations with saved history.
 *
 * Sending goes over REST, not the socket: the message is written to the
 * database first and pushed to the recipient second, so history is complete
 * even when a socket was down. The socket only delivers what is already saved.
 */
import { api, withMediaToken } from "./api";

const BASE = "/api/dm";

export type DmUser = { id: number | null; username: string };

export type DmAttachment = {
  kind: "image" | "video";
  contentType: string;
  byteSize: number | null;
  width: number | null;
  height: number | null;
  name: string | null;
  url: string;
  /** Images only — there is no server-generated poster frame for video. */
  thumbUrl: string | null;
};

export type DmMessage = {
  id: number;
  conversationId: number;
  senderId: number | null;
  senderName: string;
  mine: boolean;
  body: string | null;
  attachment: DmAttachment | null;
  createdAt: string | null;
  readAt: string | null;
};

export type DmConversation = {
  id: number;
  other: DmUser;
  /** False once the other participant has deleted their account. */
  canReply: boolean;
  unreadCount: number;
  lastMessage: DmMessage | null;
  lastMessageAt: string | null;
};

export type DmPage = { messages: DmMessage[]; hasMore: boolean };

/** Attachment URLs need the media token: <img> and <video> can't send headers. */
export function attachmentUrl(message: DmMessage, size?: "thumb"): string | null {
  if (!message.attachment) return null;
  const base = size === "thumb" ? message.attachment.thumbUrl : message.attachment.url;
  if (!base) return null;
  const url = withMediaToken(base);
  // `#t=0.1` asks the browser to seek to the first frame and paint it as the
  // poster. Without a server-side transcode that is the only way a video bubble
  // shows anything but a black rectangle — see backend/app/dm/attachments.py.
  return message.attachment.kind === "video" ? `${url}#t=0.1` : url;
}

export const dmApi = {
  conversations: () => api.get<DmConversation[]>(`${BASE}/conversations`),

  /** Get or create the thread with someone. Idempotent. */
  open: (userId: number) => api.post<DmConversation>(`${BASE}/conversations`, { userId }),

  history: (conversationId: number, before?: number, limit = 50) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (before !== undefined) params.set("before", String(before));
    return api.get<DmPage>(`${BASE}/conversations/${conversationId}/messages?${params}`);
  },

  send: (conversationId: number, body: string, file?: File | null) => {
    const form = new FormData();
    form.append("body", body);
    if (file) form.append("file", file);
    return api.form<DmMessage>(`${BASE}/conversations/${conversationId}/messages`, form);
  },

  markRead: (conversationId: number) =>
    api.post<{ markedRead: number }>(`${BASE}/conversations/${conversationId}/read`),

  remove: (messageId: number) => api.del<void>(`${BASE}/messages/${messageId}`),
};

export type DirectoryUser = { id: number; username: string };

export const userApi = {
  /** Search people to message. Returns usernames only — never emails. */
  search: (q: string) => api.get<DirectoryUser[]>(`/api/users?q=${encodeURIComponent(q)}&limit=20`),

  updateProfile: (data: { username?: string; email?: string; currentPassword?: string }) =>
    api.patch<{ id: number; email: string; username: string }>("/api/users/me", data),

  changePassword: (currentPassword: string, newPassword: string) =>
    api.post<{
      access_token: string;
      media_token: string;
      user: { id: number; email: string; username: string };
    }>("/api/users/me/password", { currentPassword, newPassword }),

  deleteAccount: (password: string) => api.del<void>("/api/users/me", { password }),
};
