import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { SAMPLE_POSTS } from "./mock";
import type { SharedTrait } from "./uploadApi";

export type User = { id: string; username: string; email: string };

export type MatchStatus = "queued" | "processing" | "done";
export type DogMatch = {
  id: string;
  userId: string;
  username: string;
  humanImg: string; // dataURL or emoji
  // Which dog, as an index into dogImages.json (see lib/dogSrc). There is no
  // breed name: AFHQ carries no breed labels, so the one that used to sit here
  // was invented by `randomBreed` independently of the photo it captioned.
  dogIndex?: number;
  sharedTraits?: SharedTrait[];
  status: MatchStatus;
  urgent: boolean;
  shared: boolean;
  createdAt: number;
};

export type Reactions = { likes: string[]; dislikes: string[] };
export type Comment = {
  id: string;
  postId: string;
  userId: string;
  username: string;
  body: string;
  media?: string;
  createdAt: number;
} & Reactions;

export type Post = {
  id: string;
  userId: string;
  username: string;
  title: string;
  body: string;
  media?: string;
  createdAt: number;
  comments: Comment[];
} & Reactions;

export type DMMessage = { id: string; from: string; body: string; media?: string; at: number };
export type Conversation = {
  id: string;
  participants: [string, string];
  usernames: [string, string];
  messages: DMMessage[];
};

// Multiplayer rooms deliberately live *only* on the server (see
// src/lib/gameSocket.ts). Keeping a copy here was what made the old lobby fake:
// localStorage is per-browser, so two people could never share a room.

export type Notification = {
  id: string;
  userId: string;
  kind: "match" | "dm" | "reaction";
  text: string;
  href?: string;
  read: boolean;
  at: number;
};

type State = {
  user: User | null;
  users: User[];
  matches: DogMatch[];
  posts: Post[];
  conversations: Conversation[];
  notifications: Notification[];
};

const KEY = "dogppleganger_v1";

function seed(): State {
  const users: User[] = [
    { id: "u_moodyoak", username: "moodyoak", email: "oak@dog.dog" },
    { id: "u_corgi_core", username: "corgi_core", email: "corgi@dog.dog" },
    { id: "u_hufflepupp", username: "hufflepupp", email: "huff@dog.dog" },
  ];
  const sampleMatches: DogMatch[] = users.map((u, i) => ({
    id: "m_seed_" + i,
    userId: u.id,
    username: u.username,
    humanImg: ["😀", "🧔", "👩‍🦱"][i],
    // Arbitrary but fixed dogs, so the cold-start gallery shows real photos
    // from the corpus instead of empty cards. These are decoration: no real
    // person was matched to them, so they carry no traits.
    dogIndex: [412, 1907, 3355][i],
    status: "done",
    urgent: false,
    shared: true,
    createdAt: Date.now() - (i + 1) * 3600_000,
  }));
  const posts: Post[] = SAMPLE_POSTS.map((p, i) => ({
    id: "p_seed_" + i,
    userId: users[i % users.length].id,
    username: users[i % users.length].username,
    title: p.title,
    body: p.body,
    createdAt: Date.now() - (i + 1) * 7200_000,
    likes: users.slice(0, (i + 1) % 3).map((u) => u.id),
    dislikes: [],
    comments: [],
  }));
  return {
    user: null,
    users,
    matches: sampleMatches,
    posts,
    conversations: [],
    notifications: [],
  };
}

function load(): State {
  if (typeof window === "undefined") return seed();
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return seed();
    return { ...seed(), ...JSON.parse(raw) };
  } catch {
    return seed();
  }
}

type Ctx = {
  state: State;
  set: (updater: (s: State) => State) => void;
  // auth
  signup: (username: string, email: string, password: string) => User;
  login: (email: string, password: string) => User | null;
  logout: () => void;
  // matches
  shareMatch: (id: string) => void;
  discardMatch: (id: string) => void;
  // posts
  addPost: (title: string, body: string, media?: string) => Post;
  toggleReact: (target: { postId: string; commentId?: string }, kind: "likes" | "dislikes") => void;
  addComment: (postId: string, body: string, media?: string) => void;
  // dms
  openConversation: (otherUserId: string, otherUsername: string) => Conversation;
  sendMessage: (conversationId: string, body: string, media?: string) => void;
  /** A real (server-side) match finished — ring the bell. */
  notifyMatchReady: (jobId: number, filename: string) => void;
  // notifications
  markAllRead: () => void;
};

const StoreCtx = createContext<Ctx | null>(null);

let idCounter = 0;
function uid(prefix: string) {
  idCounter += 1;
  return `${prefix}_${Date.now().toString(36)}_${idCounter}`;
}

export function StoreProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>(() => seed());
  const hydrated = useRef(false);

  useEffect(() => {
    setState(load());
    hydrated.current = true;
  }, []);

  useEffect(() => {
    if (!hydrated.current) return;
    try {
      localStorage.setItem(KEY, JSON.stringify(state));
    } catch {
      // Ignore storage quota / private-mode errors.
    }
  }, [state]);

  // Process queued matches: queued -> processing -> done
  useEffect(() => {
    const queued = state.matches.filter((m) => m.status !== "done");
    if (queued.length === 0) return;
    const timers = queued.map((m) => {
      const delay = m.urgent ? 1800 : 4500 + Math.random() * 2500;
      const next: MatchStatus = m.status === "queued" ? "processing" : "done";
      return setTimeout(() => {
        setState((s) => {
          const target = s.matches.find((x) => x.id === m.id);
          if (!target || target.status === "done") return s;
          const newStatus: MatchStatus = target.status === "queued" ? "processing" : "done";
          const notifs =
            newStatus === "done"
              ? [
                  {
                    id: uid("n"),
                    userId: target.userId,
                    kind: "match" as const,
                    text: "Your dog match is ready!",
                    href: `/result/${target.id}`,
                    read: false,
                    at: Date.now(),
                  },
                  ...s.notifications,
                ]
              : s.notifications;
          return {
            ...s,
            matches: s.matches.map((x) => (x.id === m.id ? { ...x, status: newStatus } : x)),
            notifications: notifs,
          };
        });
      }, delay);
    });
    return () => timers.forEach(clearTimeout);
  }, [state.matches]);

  const api = useMemo<Ctx>(() => {
    const set = (updater: (s: State) => State) => setState(updater);
    return {
      state,
      set,
      signup(username, email) {
        const u: User = { id: uid("u"), username, email };
        setState((s) => ({ ...s, users: [...s.users, u], user: u }));
        return u;
      },
      login(email) {
        const u = state.users.find((x) => x.email.toLowerCase() === email.toLowerCase());
        if (u) setState((s) => ({ ...s, user: u }));
        return u ?? null;
      },
      logout() {
        setState((s) => ({ ...s, user: null }));
      },
      shareMatch(id) {
        setState((s) => ({
          ...s,
          matches: s.matches.map((m) => (m.id === id ? { ...m, shared: true } : m)),
        }));
      },
      discardMatch(id) {
        setState((s) => ({ ...s, matches: s.matches.filter((m) => m.id !== id) }));
      },
      addPost(title, body, media) {
        const u = state.user ?? state.users[0];
        const p: Post = {
          id: uid("p"),
          userId: u.id,
          username: u.username,
          title,
          body,
          media,
          createdAt: Date.now(),
          likes: [],
          dislikes: [],
          comments: [],
        };
        setState((s) => ({ ...s, posts: [p, ...s.posts] }));
        return p;
      },
      toggleReact(target, kind) {
        const u = state.user ?? state.users[0];
        setState((s) => {
          const posts = s.posts.map((p) => {
            if (p.id !== target.postId) return p;
            if (target.commentId) {
              return {
                ...p,
                comments: p.comments.map((c) =>
                  c.id === target.commentId ? flipReact(c, kind, u.id) : c,
                ),
              };
            }
            return flipReact(p, kind, u.id);
          });
          // Notify the target owner
          let notifs = s.notifications;
          const post = s.posts.find((p) => p.id === target.postId);
          const owner = target.commentId
            ? post?.comments.find((c) => c.id === target.commentId)?.userId
            : post?.userId;
          if (owner && owner !== u.id) {
            notifs = [
              {
                id: uid("n"),
                userId: owner,
                kind: "reaction",
                text: `${u.username} ${kind === "likes" ? "liked" : "disliked"} your ${target.commentId ? "comment" : "post"}`,
                href: `/forum/${target.postId}`,
                read: false,
                at: Date.now(),
              },
              ...notifs,
            ];
          }
          return { ...s, posts, notifications: notifs };
        });
      },
      addComment(postId, body, media) {
        const u = state.user ?? state.users[0];
        setState((s) => ({
          ...s,
          posts: s.posts.map((p) =>
            p.id !== postId
              ? p
              : {
                  ...p,
                  comments: [
                    ...p.comments,
                    {
                      id: uid("c"),
                      postId,
                      userId: u.id,
                      username: u.username,
                      body,
                      media,
                      createdAt: Date.now(),
                      likes: [],
                      dislikes: [],
                    },
                  ],
                },
          ),
        }));
      },
      openConversation(otherUserId, otherUsername) {
        const me = state.user ?? state.users[0];
        const existing = state.conversations.find(
          (c) => c.participants.includes(me.id) && c.participants.includes(otherUserId),
        );
        if (existing) return existing;
        const conv: Conversation = {
          id: uid("dm"),
          participants: [me.id, otherUserId],
          usernames: [me.username, otherUsername],
          messages: [],
        };
        setState((s) => ({ ...s, conversations: [conv, ...s.conversations] }));
        return conv;
      },
      sendMessage(conversationId, body, media) {
        const me = state.user ?? state.users[0];
        setState((s) => {
          const conv = s.conversations.find((c) => c.id === conversationId);
          if (!conv) return s;
          const other = conv.participants.find((p) => p !== me.id)!;
          const msg: DMMessage = { id: uid("dm"), from: me.id, body, media, at: Date.now() };
          return {
            ...s,
            conversations: s.conversations.map((c) =>
              c.id === conversationId ? { ...c, messages: [...c.messages, msg] } : c,
            ),
            notifications: [
              {
                id: uid("n"),
                userId: other,
                kind: "dm",
                text: `New message from ${me.username}`,
                href: `/messages/${conversationId}`,
                read: false,
                at: Date.now(),
              },
              ...s.notifications,
            ],
          };
        });
      },
      notifyMatchReady(jobId, filename) {
        const u = state.user;
        if (!u) return;
        setState((s) => ({
          ...s,
          notifications: [
            {
              id: uid("n"),
              userId: u.id,
              kind: "match" as const,
              text: `Your dog for ${filename} is ready!`,
              href: `/result/${jobId}`,
              read: false,
              at: Date.now(),
            },
            ...s.notifications,
          ],
        }));
      },
      markAllRead() {
        const u = state.user;
        if (!u) return;
        setState((s) => ({
          ...s,
          notifications: s.notifications.map((n) => (n.userId === u.id ? { ...n, read: true } : n)),
        }));
      },
    };
  }, [state]);

  return <StoreCtx.Provider value={api}>{children}</StoreCtx.Provider>;
}

function flipReact<T extends Reactions>(x: T, kind: "likes" | "dislikes", uid: string): T {
  const other = kind === "likes" ? "dislikes" : "likes";
  const already = x[kind].includes(uid);
  return {
    ...x,
    [kind]: already ? x[kind].filter((i) => i !== uid) : [...x[kind], uid],
    [other]: x[other].filter((i) => i !== uid),
  } as T;
}

export function useStore() {
  const ctx = useContext(StoreCtx);
  if (!ctx) throw new Error("useStore outside StoreProvider");
  return ctx;
}

export function useCurrentUser() {
  const { state } = useStore();
  return state.user;
}
