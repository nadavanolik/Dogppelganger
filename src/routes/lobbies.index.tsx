import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { AppShell, RequireAuth } from "@/components/AppShell";
import { Leaderboard } from "@/components/game/Leaderboard";
import { ApiError, gameApi, type LeaderEntry, type RoomSummary } from "@/lib/gameApi";
import { useStore } from "@/lib/store";

export default Lobbies;

/** The list is server state, so poll it — rooms come and go from other devices. */
const POLL_MS = 3000;
const CODE_LENGTH = 4;

/** How many rows each board shows before you ask for the rest. */
const BOARD_PREVIEW = 3;

function Lobbies() {
  return (
    <AppShell>
      <RequireAuth>
        <Inner />
      </RequireAuth>
    </AppShell>
  );
}

function Inner() {
  const { state } = useStore();
  const me = state.user!;
  const navigate = useNavigate();

  const [rooms, setRooms] = useState<RoomSummary[] | null>(null);
  const [matchBoard, setMatchBoard] = useState<LeaderEntry[]>([]);
  const [doubleBoard, setDoubleBoard] = useState<LeaderEntry[]>([]);
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => {
    gameApi
      .listRooms()
      .then((res) => {
        setRooms(res.rooms);
        setError(null);
      })
      .catch((err) => {
        setRooms([]);
        setError(err instanceof ApiError ? err.message : "Couldn't load the lobby list.");
      });
  }, []);

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, POLL_MS);
    return () => window.clearInterval(id);
  }, [refresh]);

  // Each game keeps its own board — points in one aren't points in the other —
  // so both are shown rather than ranked against each other.
  useEffect(() => {
    gameApi
      .leaderboard("multiplayer_match")
      .then((res) => setMatchBoard(res.entries))
      .catch(() => setMatchBoard([]));
    gameApi
      .leaderboard("multiplayer")
      .then((res) => setDoubleBoard(res.entries))
      .catch(() => setDoubleBoard([]));
  }, []);

  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      // No game type here on purpose: the host picks it inside the room, where
      // the rounds and the clock are set too.
      const room = await gameApi.createRoom(me.id, me.username, name.trim());
      navigate(`/lobbies/${room.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't create a room.");
    } finally {
      setBusy(false);
    }
  };

  const joinByCode = async () => {
    setBusy(true);
    setError(null);
    try {
      const room = await gameApi.roomByCode(code.trim());
      navigate(`/lobbies/${room.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't find that room.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid lg:grid-cols-[1fr_20rem] gap-6 items-start">
      <div className="space-y-6">
        <header>
          <h1 className="font-display text-4xl md:text-5xl font-black">Multiplayer</h1>
          <p className="text-muted-foreground">
            Two games, same room. Everyone plays at once and sees each other move.
          </p>
        </header>

        {error && (
          <div className="card-pop-sm bg-destructive text-destructive-foreground p-3 text-sm font-bold">
            {error}
          </div>
        )}

        <div className="grid sm:grid-cols-2 gap-4">
          <div className="card-pop p-5">
            <h2 className="font-display text-xl font-black">Join with a code</h2>
            <p className="text-xs text-muted-foreground mt-1">
              The host's screen shows a 4-letter code.
            </p>
            <div className="mt-3 flex gap-2">
              <input
                value={code}
                onChange={(e) => setCode(e.target.value.toUpperCase().slice(0, CODE_LENGTH))}
                onKeyDown={(e) =>
                  e.key === "Enter" && code.length === CODE_LENGTH && void joinByCode()
                }
                placeholder="ABCD"
                aria-label="Room code"
                maxLength={CODE_LENGTH}
                className="w-32 rounded-xl border-2 border-[var(--ink)] px-3 py-2 bg-card font-display text-2xl font-black tracking-[0.3em] text-center uppercase"
              />
              <button
                disabled={code.length !== CODE_LENGTH || busy}
                onClick={() => void joinByCode()}
                className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-5 flex-1 disabled:opacity-50"
              >
                Join →
              </button>
            </div>
          </div>

          <div className="card-pop p-5">
            <h2 className="font-display text-xl font-black">Host a room</h2>
            <p className="text-xs text-muted-foreground mt-1">
              Name it, then pick the game, the rounds and the clock inside.
            </p>
            <div className="mt-3 flex gap-2">
              <input
                value={name}
                onChange={(e) => setName(e.target.value.slice(0, 60))}
                onKeyDown={(e) => e.key === "Enter" && void create()}
                placeholder="Sunday puppy jam"
                aria-label="Room name"
                className="flex-1 min-w-0 rounded-xl border-2 border-[var(--ink)] px-3 py-2 bg-card"
              />
              <button
                disabled={busy}
                onClick={() => void create()}
                className="btn-pop btn-pop-hover bg-sunshine px-5 disabled:opacity-50"
              >
                Create
              </button>
            </div>
          </div>
        </div>

        <section>
          <div className="flex items-baseline justify-between">
            <h2 className="font-display text-2xl font-black">Open rooms</h2>
            <button onClick={refresh} className="text-xs underline text-muted-foreground">
              refresh
            </button>
          </div>

          <div className="mt-3 space-y-3">
            {rooms === null && (
              <div className="card-pop-sm p-4 text-muted-foreground">Looking…</div>
            )}
            {rooms?.length === 0 && (
              <div className="card-pop-sm p-6 text-center text-muted-foreground">
                No open rooms. Host one and share the code — or{" "}
                <Link to="/game" className="underline">
                  play solo
                </Link>
                .
              </div>
            )}
            {rooms?.map((room) => (
              <div key={room.id} className="card-pop-sm p-4 flex items-center gap-3">
                <div className="text-4xl">{room.gameType === "match" ? "🔗" : "🎯"}</div>
                <div className="flex-1 min-w-0">
                  <div className="font-display text-xl font-bold truncate">{room.name}</div>
                  <div className="text-xs text-muted-foreground">
                    {room.gameType === "match" ? "Mix & match" : "Spot the double"} · hosted by @
                    {room.hostName} · {room.playerCount} player
                    {room.playerCount === 1 ? "" : "s"} · {room.roundsTotal} rounds ·{" "}
                    {room.secondsPerQuestion}s{room.phase === "over" && " · just finished"}
                  </div>
                </div>
                <code className="hidden sm:block font-display text-lg font-black tracking-[0.2em] px-2">
                  {room.code}
                </code>
                <button
                  onClick={() => navigate(`/lobbies/${room.id}`)}
                  className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-4 py-2 text-sm"
                >
                  Join
                </button>
              </div>
            ))}
          </div>
        </section>
      </div>

      <div className="space-y-4">
        <Leaderboard
          entries={matchBoard}
          board="multiplayer_match"
          meId={me.id}
          title="🔗 Mix & match"
          collapsedTo={BOARD_PREVIEW}
          empty="No games finished yet."
        />
        <Leaderboard
          entries={doubleBoard}
          board="multiplayer"
          meId={me.id}
          title="🎯 Spot the double"
          collapsedTo={BOARD_PREVIEW}
          empty="No games finished yet."
        />
      </div>
    </div>
  );
}
