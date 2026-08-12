import type { LeaderEntry } from "@/lib/gameApi";

const MEDALS = ["🥇", "🥈", "🥉"];

/**
 * A leaderboard, shared by every player and persisted on the server.
 *
 * The solo board ranks by how far you got; the multiplayer board ranks by wins.
 */
export function Leaderboard({
  entries,
  board,
  meId,
  title,
  empty = "Nobody has played yet. Be first.",
}: {
  entries: LeaderEntry[];
  board: "solo" | "multiplayer";
  meId?: string | null;
  title: string;
  empty?: string;
}) {
  return (
    <div className="card-pop p-5">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="font-display text-xl font-black">{title}</h2>
        <span className="text-xs text-muted-foreground">
          {board === "solo" ? "best run" : "wins"}
        </span>
      </div>

      {entries.length === 0 ? (
        <p className="text-sm text-muted-foreground mt-3">{empty}</p>
      ) : (
        <ol className="mt-3 space-y-2">
          {entries.map((e, i) => (
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
                  {board === "solo" ? e.best : e.wins}
                </span>
                <span className="block text-[11px] text-muted-foreground leading-none">
                  {board === "solo"
                    ? `streak ${e.longestStreak} · ${e.gamesPlayed} run${e.gamesPlayed === 1 ? "" : "s"}`
                    : `best ${e.best.toLocaleString()} · ${e.gamesPlayed} game${e.gamesPlayed === 1 ? "" : "s"}`}
                </span>
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
