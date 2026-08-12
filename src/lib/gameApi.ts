/**
 * REST client for `/api/game`.
 *
 * Covers everything without a clock: lobby discovery, the untimed solo run, and
 * leaderboards. Anything live (the multiplayer room) goes over the socket in
 * `gameSocket.ts` instead.
 */

const BASE = "/api/game";

export type Question = {
  index: number;
  itemId: string;
  humanSeed: string;
  humanUrl: string | null;
  options: number[]; // dog indices — see dogSrc()
};

export type SoloState = {
  runToken: string;
  lives: number;
  score: number;
  streak: number;
  longestStreak: number;
  over: boolean;
  question: Question | null;
};

export type SoloResult = SoloState & {
  wasCorrect: boolean;
  answerIndex: number;
  leaderboard?: LeaderEntry[];
  rank?: number | null;
};

export type LeaderEntry = {
  playerId: string;
  name: string;
  best: number;
  longestStreak: number;
  gamesPlayed: number;
  wins: number;
  updatedAt: string;
};

export type RoomSummary = {
  id: string;
  code: string;
  name: string;
  phase: RoomPhase;
  hostName: string;
  playerCount: number;
  roundsTotal: number;
  secondsPerQuestion: number;
};

export type RoomPhase = "lobby" | "countdown" | "question" | "reveal" | "over";

export type RoomPlayer = {
  playerId: string;
  name: string;
  score: number;
  streak: number;
  connected: boolean;
  isHost: boolean;
  answered: boolean;
  lastAward: number;
  lastCorrect: boolean | null;
};

export type RoomState = {
  id: string;
  code: string;
  name: string;
  phase: RoomPhase;
  hostId: string;
  roundsTotal: number;
  secondsPerQuestion: number;
  questionNumber: number;
  question: Question | null;
  answerIndex: number | null;
  endsAt: number | null;
  serverNow: number;
  players: RoomPlayer[];
  isLastQuestion?: boolean;
  leaderboard?: LeaderEntry[];
};

export class ApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: init?.body ? { "Content-Type": "application/json" } : undefined,
    });
  } catch {
    throw new ApiError("Can't reach the server. Is the backend running?");
  }
  if (!res.ok) {
    // FastAPI puts the human-readable reason in `detail`.
    const body = await res.json().catch(() => null);
    const detail = body?.detail;
    throw new ApiError(typeof detail === "string" ? detail : `Request failed (${res.status}).`);
  }
  return res.json() as Promise<T>;
}

export const gameApi = {
  listRooms: () =>
    request<{ rooms: RoomSummary[]; options: { rounds: number[]; seconds: number[] } }>("/rooms"),

  createRoom: (playerId: string, playerName: string, name: string) =>
    request<RoomSummary>("/rooms", {
      method: "POST",
      body: JSON.stringify({ playerId, playerName, name }),
    }),

  roomByCode: (code: string) => request<RoomSummary>(`/rooms/by-code/${encodeURIComponent(code)}`),

  soloStart: (playerId: string, playerName: string) =>
    request<SoloState>("/solo/start", {
      method: "POST",
      body: JSON.stringify({ playerId, playerName }),
    }),

  soloAnswer: (runToken: string, choice: number) =>
    request<SoloResult>("/solo/answer", {
      method: "POST",
      body: JSON.stringify({ runToken, choice }),
    }),

  leaderboard: (board: "solo" | "multiplayer", limit = 20) =>
    request<{ board: string; entries: LeaderEntry[] }>(`/leaderboard/${board}?limit=${limit}`),
};
