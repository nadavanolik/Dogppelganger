import { createFileRoute, Link } from "@tanstack/react-router";
import { AppShell, RequireAuth } from "@/components/AppShell";

export const Route = createFileRoute("/play")({ component: PlayHub });

function PlayHub() {
  return (
    <AppShell>
      <RequireAuth>
        <div className="max-w-4xl mx-auto space-y-8">
          <header className="text-center">
            <h1 className="font-display text-5xl md:text-6xl font-black">Play</h1>
            <p className="text-muted-foreground mt-2">Match humans to their dog doubles. Solo drills or live with friends.</p>
          </header>
          <div className="grid md:grid-cols-2 gap-6">
            <Link to="/game" className="card-pop p-8 hover:-translate-y-1 transition block">
              <div className="text-7xl">🎯</div>
              <div className="mt-4 font-display text-3xl font-black">Solo</div>
              <p className="text-muted-foreground mt-1">Quick single-player breed-guessing rounds. Beat your own high score.</p>
              <div className="mt-4 inline-block btn-pop bg-sunshine px-4 py-2 text-sm">Start solo →</div>
            </Link>
            <Link to="/lobbies" className="card-pop p-8 hover:-translate-y-1 transition block">
              <div className="text-7xl">👥</div>
              <div className="mt-4 font-display text-3xl font-black">Multiplayer</div>
              <p className="text-muted-foreground mt-1">Join or host a lobby. Live scoreboard, same rounds for everyone.</p>
              <div className="mt-4 inline-block btn-pop bg-primary text-primary-foreground px-4 py-2 text-sm">Find a lobby →</div>
            </Link>
          </div>
        </div>
      </RequireAuth>
    </AppShell>
  );
}
