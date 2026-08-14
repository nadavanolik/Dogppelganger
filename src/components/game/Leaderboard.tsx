import { useState } from "react";

import type { BoardName, LeaderEntry } from "@/lib/gameApi";

const MEDALS = ["🥇", "🥈", "🥉"];

/**
 * A leaderboard, shared by every player and persisted on the server.
 *
 * Solo boards rank by how far you got; multiplayer boards rank by wins. Each
 * game mode has its own, because a Streak Survival score counts answers and a
 * Mix & Match score counts points.
 *
 * `collapsedTo` caps how many rows show until the reader asks for the rest —
 * for pages that stack several boards and can't give any of them the height.
 */
export function Leaderboard({
  entries,
  board,
  meId,
  title,
  collapsedTo,
  empty = "Nobody has played yet. Be first.",
}: {
  entries: LeaderEntry[];
  board: BoardName;
  meId?: string | null;
  title: string;
  collapsedTo?: number;
  empty?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const ranksByWins = board.startsWith("multiplayer");
  const collapsible = collapsedTo !== undefined && entries.length > collapsedTo;
  const shown = collapsible && !expanded ? entries.slice(0, collapsedTo) : entries;

  return (
    <div className="card-pop p-5">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="font-display text-xl font-black">{title}</h2>
        <span className="text-xs text-muted-foreground">{ranksByWins ? "wins" : "best run"}</span>
      </div>

      {entries.length === 0 ? (
        <p className="text-sm text-muted-foreground mt-3">{empty}</p>
      ) : (
        <ol className="mt-3 space-y-2">
          {shown.map((e, i) => (
            <li
              key={e.playerId}
              className={`flex items-center gap-2 px-3 py-2 rounded-xl border-2 border-[var(--ink)] ${
                e.playerId === meId ? "bg-sunshine" : "bg-card"
              }`}
            >
              <span className="w-6 text-center">{MEDALS[i] ?? i + 1}</span>
              <span className="flex-1 font-bold truncate">@{e.name}</span>
              <span className="text-right">
                <span className="font-display text-lg font-black">
                  {ranksByWins ? e.wins : e.best}
                </span>
                <span className="block text-[11px] text-muted-foreground leading-none">
                  {ranksByWins
                    ? `best ${e.best.toLocaleString()} · ${e.gamesPlayed} game${e.gamesPlayed === 1 ? "" : "s"}`
                    : `streak ${e.longestStreak} · ${e.gamesPlayed} run${e.gamesPlayed === 1 ? "" : "s"}`}
                </span>
              </span>
            </li>
          ))}
        </ol>
      )}

      {collapsible && (
        <button
          onClick={() => setExpanded((open) => !open)}
          aria-expanded={expanded}
          className="mt-3 w-full text-xs font-bold underline text-muted-foreground"
        >
          {expanded ? "Show less" : `Show all ${entries.length}`}
        </button>
      )}
    </div>
  );
}
