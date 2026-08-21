/**
 * REST client for `/api/game`.
 *
 * Covers everything without a clock: lobby discovery, the untimed solo run, and
 * leaderboards. Anything live (the multiplayer room) goes over the socket in
 * `gameSocket.ts` instead.
 */

import { api } from "./api";

// One error type for the whole app now — re-exported so existing call sites
// keep working. See src/lib/api.ts.
export { ApiError } from "./api";

const BASE = "/api/game";

/** Spot the Double (one human, N dogs) or Mix & Match (four of each). */
export type GameType = "double" | "match";

/** Each mode keeps its own board: answers and points aren't the same currency. */
export type BoardName = "solo" | "multiplayer" | "solo_match" | "multiplayer_match";

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

// ------------------------------------------------------------- Mix & Match

export type BoardHuman = { slot: number; id: string; humanSeed: string; humanUrl: string | null };
export type BoardDog = { slot: number; dogIndex: number };

/** The dealt board. Slots are positions in these arrays — a claim is two ints. */
export type MatchBoard = { humans: BoardHuman[]; dogs: BoardDog[] };

/** Who holds which human↔dog combination. Public on purpose: it's the game. */
export type Claim = { human: number; dog: number; playerId: string; name: string };

/** human slot -> dog slot. Object keys arrive from JSON as strings. */
export type PairMap = Record<string, number>;

export type SoloMatchState = {
  runToken: string;
  lives: number;
  score: number;
  boardsPlayed: number;
  streak: number;
  longestStreak: number;
  over: boolean;
  board: MatchBoard | null;
};

export type SoloMatchResult = SoloMatchState & {
  wasPerfect: boolean;
  roundCorrect: number;
  marks: Record<string, boolean>;
  boardAnswer: PairMap;
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
  gameType: GameType;
  phase: RoomPhase;
  hostName: string;
  playerCount: number;
  roundsTotal: number;
  secondsPerQuestion: number;
};

export type RoomOptions = {
  rounds: number[];
  seconds: number[];
  matchSeconds: number[];
  gameTypes: GameType[];
};

export type RoomPhase = "lobby" | "countdown" | "question" | "reveal" | "over";

export type RoomPlayer = {
  playerId: string;
  name: string;
  score: number;
  streak: number;
  connected: boolean;
  isHost: boolean;
  /** Nothing left to do this round — answered, or submitted a board. */
  answered: boolean;
  submitted: boolean;
  lastAward: number;
  lastCorrect: boolean | null;
  lastRoundCorrect: number;
};

export type RoomState = {
  id: string;
  code: string;
  name: string;
  gameType: GameType;
  phase: RoomPhase;
  hostId: string;
  roundsTotal: number;
  secondsPerQuestion: number;
  questionNumber: number;
  // Exactly one of `question` / `board` is populated, decided by `gameType`.
  question: Question | null;
  answerIndex: number | null;
  board: MatchBoard | null;
  boardAnswer: PairMap | null;
  claims: Claim[];
  endsAt: number | null;
  serverNow: number;
  players: RoomPlayer[];
  isLastQuestion?: boolean;
  leaderboard?: LeaderEntry[];
};

export const gameApi = {
  listRooms: () => api.get<{ rooms: RoomSummary[]; options: RoomOptions }>(`${BASE}/rooms`),

  /** `gameType` is optional: the host normally picks it in the room instead. */
  createRoom: (name: string, gameType?: GameType) =>
    api.post<RoomSummary>(`${BASE}/rooms`, { name, ...(gameType ? { gameType } : {}) }),

  roomByCode: (code: string) =>
    api.get<RoomSummary>(`${BASE}/rooms/by-code/${encodeURIComponent(code)}`),

  // No player argument on any of these any more: a run belongs to whoever
  // started it, and the server checks that the token submitting an answer is
  // the one that started the run.
  soloStart: () => api.post<SoloState>(`${BASE}/solo/start`),

  soloAnswer: (runToken: string, choice: number) =>
    api.post<SoloResult>(`${BASE}/solo/answer`, { runToken, choice }),

  soloMatchStart: () => api.post<SoloMatchState>(`${BASE}/solo/match/start`),

  soloMatchSubmit: (runToken: string, pairs: PairMap) =>
    api.post<SoloMatchResult>(`${BASE}/solo/match/submit`, { runToken, pairs }),

  leaderboard: (board: BoardName, limit = 20) =>
    api.get<{ board: string; entries: LeaderEntry[] }>(
      `${BASE}/leaderboard/${board}?limit=${limit}`,
    ),
};
