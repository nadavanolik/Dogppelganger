import { createFileRoute, Link, useRouter } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { AppShell, RequireAuth } from "@/components/AppShell";
import { BREEDS } from "@/lib/mock";
import { useStore } from "@/lib/store";

export const Route = createFileRoute("/lobbies/$id")({ component: Room });

function Room() {
  return <AppShell><RequireAuth><Inner /></RequireAuth></AppShell>;
}

function Inner() {
  const { id } = Route.useParams();
  const { state, leaveLobby, advanceLobbyRound, submitLobbyGuess } = useStore();
  const router = useRouter();
  const lobby = state.lobbies.find((l) => l.id === id);
  const [picked, setPicked] = useState<string | null>(null);
  const match = lobby?.currentMatchId ? state.matches.find((m) => m.id === lobby.currentMatchId) : null;

  const choices = useMemo(() => {
    if (!match) return [];
    const others = BREEDS.filter((b) => b.name !== match.breedName).sort(() => Math.random() - 0.5).slice(0, 3).map(b => b.name);
    return [...others, match.breedName].sort(() => Math.random() - 0.5);
  }, [match?.id]);

  if (!lobby) return <div className="card-pop p-8 text-center">Lobby closed. <Link to="/lobbies" className="underline">Back</Link></div>;

  const me = state.user!;
  const inGame = lobby.players.some((p) => p.id === me.id);

  return (
    <div className="grid md:grid-cols-3 gap-6">
      <div className="md:col-span-2 card-pop p-6">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-bold text-muted-foreground">Lobby</div>
            <h1 className="font-display text-3xl font-black">{lobby.name}</h1>
          </div>
          <div className="btn-pop bg-sunshine px-3 py-1">Round {lobby.round}</div>
        </div>

        {!match ? (
          <div className="mt-8 text-center">
            <div className="text-6xl">🎬</div>
            <div className="font-display text-2xl font-bold mt-2">Waiting to start</div>
            <p className="text-muted-foreground">Host, kick off the first round when players are in.</p>
            {lobby.hostId === me.id && (
              <button onClick={() => { setPicked(null); advanceLobbyRound(lobby.id); }} className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-5 py-2 mt-4">Start round</button>
            )}
          </div>
        ) : (
          <div className="mt-6">
            <div className="text-sm font-bold text-muted-foreground text-center">Everyone sees the same photo. Pick the breed.</div>
            <div className="flex justify-center mt-3">
              {match.humanImg.startsWith("data:") ? (
                <img src={match.humanImg} className="h-56 w-56 rounded-2xl border-2 border-[var(--ink)] object-cover" alt="" />
              ) : (
                <div className="h-56 w-56 rounded-2xl border-2 border-[var(--ink)] bg-sky flex items-center justify-center text-8xl">{match.humanImg}</div>
              )}
            </div>
            <div className="grid grid-cols-2 gap-3 mt-6">
              {choices.map((c) => {
                const right = c === match.breedName;
                const tint = picked == null ? "bg-card" : c === picked ? (right ? "bg-mint" : "bg-destructive text-destructive-foreground") : right ? "bg-mint" : "opacity-60";
                return (
                  <button
                    key={c}
                    disabled={picked !== null}
                    onClick={() => { setPicked(c); submitLobbyGuess(lobby.id, right); }}
                    className={`btn-pop btn-pop-hover px-4 py-3 text-lg ${tint}`}
                  >{c}</button>
                );
              })}
            </div>
            {picked && (
              <div className="text-center mt-6">
                <div className="text-2xl">Answer: {match.breedEmoji} {match.breedName}</div>
                {lobby.hostId === me.id && (
                  <button onClick={() => { setPicked(null); advanceLobbyRound(lobby.id); }} className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-5 py-2 mt-3">Next round →</button>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      <aside className="card-pop p-5 h-fit">
        <div className="font-display text-xl font-black">Live scoreboard</div>
        <ul className="mt-3 space-y-2">
          {[...lobby.players].sort((a,b) => b.score - a.score).map((p, i) => (
            <li key={p.id} className={`flex items-center justify-between px-3 py-2 rounded-xl border-2 border-[var(--ink)] ${p.id === me.id ? "bg-sunshine" : "bg-card"}`}>
              <span className="font-bold">{i === 0 ? "🥇" : i === 1 ? "🥈" : i === 2 ? "🥉" : "🐾"} @{p.name}</span>
              <span className="font-display text-xl font-black">{p.score}</span>
            </li>
          ))}
        </ul>
        {inGame ? (
          <button onClick={() => { leaveLobby(lobby.id); router.navigate({ to: "/lobbies" }); }} className="btn-pop btn-pop-hover bg-card w-full py-2 mt-4">Leave lobby</button>
        ) : (
          <Link to="/lobbies" className="btn-pop btn-pop-hover bg-primary text-primary-foreground w-full py-2 mt-4 block text-center">Back to lobbies</Link>
        )}
        <div className="mt-4 text-xs text-muted-foreground">Prototype: shared state is per-browser. In production this room would sync over websockets, server-authoritative.</div>
      </aside>
    </div>
  );
}
