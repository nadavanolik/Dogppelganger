import { Link } from "react-router-dom";
import { AppShell, RequireAuth } from "@/components/AppShell";

export default PlayHub;

function PlayHub() {
  return (
    <AppShell>
      <RequireAuth>
        <div className="max-w-4xl mx-auto space-y-8">
          <header className="text-center">
            <h1 className="font-display text-5xl md:text-6xl font-black">Play</h1>
            <p className="text-muted-foreground mt-2">
              Match humans to their dog doubles. Alone against your own record, or live against
              everyone else.
            </p>
          </header>
          <div className="grid md:grid-cols-2 gap-6">
            <Link to="/game" className="card-pop p-8 hover:-translate-y-1 transition block">
              <div className="text-7xl">🎯</div>
              <div className="mt-4 font-display text-3xl font-black">Streak survival</div>
              <p className="text-muted-foreground mt-1">
                No timer, three lives. Keep picking the right dog and see how far you get — best
                runs go on the board.
              </p>
              <div className="mt-4 inline-block btn-pop bg-sunshine px-4 py-2 text-sm">
                Start solo →
              </div>
            </Link>
            <Link to="/lobbies" className="card-pop p-8 hover:-translate-y-1 transition block">
              <div className="text-7xl">👥</div>
              <div className="mt-4 font-display text-3xl font-black">Multiplayer race</div>
              <p className="text-muted-foreground mt-1">
                Host a room, share the 4-letter code. Same question for everyone at once, and the
                faster you answer the more it's worth.
              </p>
              <div className="mt-4 inline-block btn-pop bg-primary text-primary-foreground px-4 py-2 text-sm">
                Find a room →
              </div>
            </Link>
          </div>
        </div>
      </RequireAuth>
    </AppShell>
  );
}
