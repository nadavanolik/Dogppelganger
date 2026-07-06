import { createFileRoute, Link, useRouter } from "@tanstack/react-router";
import { useState } from "react";
import { AppShell, RequireAuth } from "@/components/AppShell";
import { useStore } from "@/lib/store";

export const Route = createFileRoute("/lobbies/")({ component: Lobbies });

function Lobbies() {
  return <AppShell><RequireAuth><Inner /></RequireAuth></AppShell>;
}

function Inner() {
  const { state, createLobby, joinLobby } = useStore();
  const router = useRouter();
  const [name, setName] = useState("");
  return (
    <div className="grid md:grid-cols-3 gap-6">
      <div className="md:col-span-2">
        <h1 className="font-display text-4xl font-black">Multiplayer lobbies</h1>
        <p className="text-muted-foreground">Shared game state, live scoreboard, server-authoritative rounds.</p>
        <div className="mt-6 space-y-3">
          {state.lobbies.length === 0 && <div className="card-pop p-6 text-muted-foreground">No open lobbies. Start one →</div>}
          {state.lobbies.map((l) => (
            <div key={l.id} className="card-pop-sm p-4 flex items-center gap-3">
              <div className="text-4xl">🎪</div>
              <div className="flex-1">
                <div className="font-display text-xl font-bold">{l.name}</div>
                <div className="text-xs text-muted-foreground">hosted by @{l.hostName} · {l.players.length} player{l.players.length === 1 ? "" : "s"} · {l.status}</div>
              </div>
              <button
                onClick={() => { joinLobby(l.id); router.navigate({ to: `/lobbies/${l.id}` }); }}
                className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-4 py-2 text-sm"
              >
                Join
              </button>
            </div>
          ))}
        </div>
      </div>
      <div className="card-pop p-5 h-fit">
        <div className="font-display text-xl font-black">Create lobby</div>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Sunday puppy jam" className="mt-3 w-full rounded-xl border-2 border-[var(--ink)] px-3 py-2 bg-card" />
        <button
          disabled={!name.trim()}
          onClick={() => {
            const lb = createLobby(name.trim());
            router.navigate({ to: `/lobbies/${lb.id}` });
          }}
          className="btn-pop btn-pop-hover bg-primary text-primary-foreground w-full py-2 mt-3 disabled:opacity-50"
        >Create & join</button>
        <Link to="/game" className="block text-center text-sm underline mt-4">or play solo →</Link>
      </div>
    </div>
  );
}
