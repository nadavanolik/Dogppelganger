import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { AppShell, RequireAuth } from "@/components/AppShell";
import { DogOption, QuestionPrompt } from "@/components/game/DogOption";
import { HumanFace } from "@/components/game/HumanFace";
import { Leaderboard } from "@/components/game/Leaderboard";
import { Podium, Scoreboard } from "@/components/game/Scoreboard";
import { TimerBar } from "@/components/game/TimerBar";
import { useGameRoom } from "@/lib/gameSocket";
import { useStore } from "@/lib/store";
import { useSecondsLeft } from "@/lib/useCountdown";

export default Room;

const OPTION_LABELS = ["1", "2", "3", "4"];
const ROUND_CHOICES = [5, 8, 10, 15, 20];
const SECOND_CHOICES = [10, 15, 20];
const NOTICE_MS = 3500;

function Room() {
  return (
    <AppShell>
      <RequireAuth>
        <Inner />
      </RequireAuth>
    </AppShell>
  );
}

function Inner() {
  const { id } = useParams();
  const { state: store } = useStore();
  const me = store.user!;
  const navigate = useNavigate();

  const { status, state, notice, clearNotice, serverNow, send } = useGameRoom({
    playerId: me.id,
    playerName: me.username,
    roomId: id,
  });

  // What *I* clicked. The server decides whether it counted; this only stops me
  // hammering the same question and shows my choice back to me.
  const [picked, setPicked] = useState<number | null>(null);
  useEffect(() => setPicked(null), [state?.questionNumber]);

  useEffect(() => {
    if (!notice) return;
    const t = window.setTimeout(clearNotice, NOTICE_MS);
    return () => window.clearTimeout(t);
  }, [notice, clearNotice]);

  const phase = state?.phase;
  const question = state?.question ?? null;

  const answer = useCallback(
    (choice: number) => {
      if (phase !== "question" || !question || picked !== null) return;
      setPicked(choice);
      send("answer", { questionIndex: question.index, choice });
    },
    [phase, question, picked, send],
  );

  useEffect(() => {
    if (phase !== "question" || !question || picked !== null) return;
    const onKey = (e: KeyboardEvent) => {
      const index = OPTION_LABELS.indexOf(e.key);
      if (index >= 0 && index < question.options.length) {
        e.preventDefault();
        answer(index);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [phase, question, picked, answer]);

  const leave = () => {
    send("leave");
    navigate("/lobbies");
  };

  const isHost = state?.hostId === me.id;
  const countdown = useSecondsLeft(
    phase === "countdown" ? (state?.endsAt ?? null) : null,
    serverNow,
  );

  if (!state) {
    return (
      <div className="card-pop max-w-md mx-auto p-8 text-center">
        <div className="text-5xl">{status === "open" ? "🐕" : "🔌"}</div>
        <h1 className="font-display text-2xl font-black mt-2">
          {status === "open" ? "Joining the room…" : "Connecting…"}
        </h1>
        {notice && <p className="text-sm font-bold mt-2">{notice}</p>}
        <Link to="/lobbies" className="btn-pop btn-pop-hover bg-card px-4 py-2 mt-4 inline-block">
          Back to lobbies
        </Link>
      </div>
    );
  }

  return (
    <div className="grid lg:grid-cols-[1fr_20rem] gap-6 items-start">
      <div className="space-y-4">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="text-xs font-bold text-muted-foreground uppercase tracking-wide">
              Room
            </div>
            <h1 className="font-display text-3xl font-black truncate">{state.name}</h1>
          </div>
          <div className="flex items-center gap-2">
            {phase !== "lobby" && phase !== "over" && (
              <div className="btn-pop bg-sunshine px-3 py-1 text-sm">
                Round {state.questionNumber} / {state.roundsTotal}
              </div>
            )}
            <button onClick={leave} className="btn-pop btn-pop-hover bg-card px-4 py-2 text-sm">
              Leave
            </button>
          </div>
        </header>

        {status !== "open" && (
          <div className="card-pop-sm bg-sky p-3 text-sm font-bold">
            Reconnecting… your score is safe on the server.
          </div>
        )}
        {notice && (
          <div className="card-pop-sm bg-destructive text-destructive-foreground p-3 text-sm font-bold">
            {notice}
          </div>
        )}

        {phase === "lobby" && (
          <div className="card-pop p-8 text-center">
            <div className="text-xs font-bold text-muted-foreground uppercase tracking-wide">
              Room code
            </div>
            <div className="font-display text-6xl font-black tracking-[0.25em] mt-1">
              {state.code}
            </div>
            <p className="text-muted-foreground mt-2">
              Others join from <strong>Multiplayer</strong> with this code — phones included.
            </p>

            {isHost ? (
              <div className="mt-6 space-y-4">
                <div className="flex flex-wrap gap-4 justify-center">
                  <Chooser
                    label="Rounds"
                    values={ROUND_CHOICES}
                    current={state.roundsTotal}
                    onPick={(v) => send("set_options", { roundsTotal: v })}
                  />
                  <Chooser
                    label="Seconds each"
                    values={SECOND_CHOICES}
                    current={state.secondsPerQuestion}
                    onPick={(v) => send("set_options", { secondsPerQuestion: v })}
                  />
                </div>
                <button
                  onClick={() => send("start")}
                  className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-8 py-3 text-lg"
                >
                  Start game →
                </button>
              </div>
            ) : (
              <p className="mt-6 font-bold">Waiting for the host to start…</p>
            )}
          </div>
        )}

        {phase === "countdown" && (
          <div className="card-pop p-16 text-center">
            <div className="font-display text-8xl font-black">{countdown || "Go!"}</div>
            <p className="text-muted-foreground mt-2">Get ready…</p>
          </div>
        )}

        {(phase === "question" || phase === "reveal") && question && (
          <div className="card-pop p-6">
            {phase === "question" ? (
              <TimerBar
                endsAt={state.endsAt}
                durationMs={state.secondsPerQuestion * 1000}
                serverNow={serverNow}
                label={picked === null ? "Pick a dog" : "Locked in — waiting for the others"}
              />
            ) : (
              <div className="text-center font-display text-2xl font-black">
                {state.answerIndex !== null && `The answer was ${OPTION_LABELS[state.answerIndex]}`}
              </div>
            )}

            <div className="mt-6">
              <QuestionPrompt>
                <HumanFace
                  seed={question.humanSeed}
                  url={question.humanUrl}
                  className="h-40 w-40 rounded-2xl border-2 border-[var(--ink)]"
                />
              </QuestionPrompt>
            </div>

            <div className="mt-6 grid grid-cols-2 sm:grid-cols-4 gap-3">
              {question.options.map((dogIndex, i) => (
                <DogOption
                  key={`${question.itemId}-${i}`}
                  dogIndex={dogIndex}
                  label={OPTION_LABELS[i]}
                  disabled={phase === "reveal" || picked !== null}
                  state={
                    phase === "reveal"
                      ? i === state.answerIndex
                        ? "correct"
                        : i === picked
                          ? "wrong"
                          : "dimmed"
                      : i === picked
                        ? "picked"
                        : "idle"
                  }
                  onClick={() => answer(i)}
                />
              ))}
            </div>

            {phase === "question" && (
              <p className="text-center text-xs text-muted-foreground mt-4">
                {picked === null
                  ? "Faster answers score more — tap a dog or press 1–4."
                  : "Answer locked. No changing your mind."}
              </p>
            )}
          </div>
        )}

        {phase === "over" && (
          <div className="card-pop p-8">
            <Podium players={state.players} meId={me.id} />
            <div className="mt-8 flex gap-3 justify-center flex-wrap">
              {isHost ? (
                <button
                  onClick={() => send("again")}
                  className="btn-pop btn-pop-hover bg-primary text-primary-foreground px-6 py-3"
                >
                  Play again →
                </button>
              ) : (
                <span className="text-muted-foreground font-bold self-center">
                  Waiting for the host to run it back…
                </span>
              )}
              <Link to="/lobbies" className="btn-pop btn-pop-hover bg-card px-6 py-3">
                Back to lobbies
              </Link>
            </div>
          </div>
        )}

        {phase === "over" && state.leaderboard && (
          <Leaderboard
            entries={state.leaderboard}
            board="multiplayer"
            meId={me.id}
            title="🏅 Most wins, all-time"
          />
        )}
      </div>

      <Scoreboard players={state.players} meId={me.id} phase={state.phase} />
    </div>
  );
}

function Chooser({
  label,
  values,
  current,
  onPick,
}: {
  label: string;
  values: number[];
  current: number;
  onPick: (value: number) => void;
}) {
  return (
    <div>
      <div className="text-xs font-bold text-muted-foreground uppercase tracking-wide mb-1">
        {label}
      </div>
      <div className="flex gap-1">
        {values.map((v) => (
          <button
            key={v}
            onClick={() => onPick(v)}
            className={`btn-pop btn-pop-hover px-3 py-1 text-sm ${
              v === current ? "bg-primary text-primary-foreground" : "bg-card"
            }`}
          >
            {v}
          </button>
        ))}
      </div>
    </div>
  );
}
