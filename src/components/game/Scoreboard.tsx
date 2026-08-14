import type { RoomPlayer } from "@/lib/gameApi";

const MEDALS = ["🥇", "🥈", "🥉"];

/**
 * The live scoreboard for a room.
 *
 * Already sorted by the server, so every screen shows the same order. During a
 * question it shows who has locked in — but never what they picked.
 */
export function Scoreboard({
  players,
  meId,
  phase,
}: {
  players: RoomPlayer[];
  meId: string | null;
  phase: string;
}) {
  const revealing = phase === "reveal" || phase === "over";

  return (
    <div className="card-pop p-5 h-fit">
      <div className="flex items-baseline justify-between">
        <h2 className="font-display text-xl font-black">Scoreboard</h2>
        <span className="text-xs text-muted-foreground">
          {players.length} player{players.length === 1 ? "" : "s"}
        </span>
      </div>

      <ul className="mt-3 space-y-2">
        {players.map((p, i) => (
          <li
            key={p.playerId}
            className={`flex items-center gap-2 px-3 py-2 rounded-xl border-2 border-[var(--ink)] ${
              p.playerId === meId ? "bg-sunshine" : "bg-card"
            } ${p.connected ? "" : "opacity-50"}`}
          >
            <span className="w-6 text-center">{MEDALS[i] ?? "🐾"}</span>
            <span className="flex-1 min-w-0">
              <span className="font-bold truncate block">
                @{p.name} {p.isHost && <span title="host">👑</span>}
              </span>
              <span className="text-[11px] text-muted-foreground leading-none">
                {!p.connected
                  ? "away"
                  : phase === "question"
                    ? p.answered
                      ? "locked in ✔"
                      : "thinking…"
                    : p.streak > 1
                      ? `🔥 ${p.streak} in a row`
                      : " "}
              </span>
            </span>
            <span className="text-right">
              <span className="font-display text-lg font-black">{p.score.toLocaleString()}</span>
              {revealing && p.lastAward > 0 && (
                <span className="block text-[11px] font-bold text-[color:var(--mint-foreground)] leading-none">
                  +{p.lastAward}
                </span>
              )}
              {revealing && p.lastCorrect === false && (
                <span className="block text-[11px] text-muted-foreground leading-none">missed</span>
              )}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** End-of-game podium. */
export function Podium({ players, meId }: { players: RoomPlayer[]; meId: string | null }) {
  const top = players.slice(0, 3);
  const winner = players[0];
  const iWon = winner && winner.playerId === meId;

  return (
    <div className="text-center">
      <div className="text-6xl">{iWon ? "🏆" : "🎉"}</div>
      <h2 className="font-display text-4xl font-black mt-2">
        {winner ? `@${winner.name} wins!` : "Game over"}
      </h2>
      {iWon && <p className="text-muted-foreground">That's you. Top dog.</p>}

      <div className="mt-6 flex items-end justify-center gap-3">
        {top.map((p, i) => (
          <div key={p.playerId} className="flex flex-col items-center">
            <div className="text-3xl">{MEDALS[i]}</div>
            <div
              className={`card-pop-sm w-24 flex flex-col justify-end p-2 ${
                p.playerId === meId ? "bg-sunshine" : "bg-card"
              }`}
              style={{ height: [120, 90, 70][i] }}
            >
              <div className="font-display text-xl font-black">{p.score.toLocaleString()}</div>
              <div className="text-xs truncate">@{p.name}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
